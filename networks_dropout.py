import torch
from torch import nn


class IMVTensorLSTM_dropout(torch.jit.ScriptModule):
    
    __constants__ = ["n_units", "input_dim"]
    def __init__(self, input_dim, output_dim, n_units, init_std=0.02, p=0.1):
        super().__init__()
        self.U_j = nn.Parameter(torch.randn(input_dim, 1, n_units)*init_std)
        self.U_i = nn.Parameter(torch.randn(input_dim, 1, n_units)*init_std)
        self.U_f = nn.Parameter(torch.randn(input_dim, 1, n_units)*init_std)
        self.U_o = nn.Parameter(torch.randn(input_dim, 1, n_units)*init_std)
        self.W_j = nn.Parameter(torch.randn(input_dim, n_units, n_units)*init_std)
        self.W_i = nn.Parameter(torch.randn(input_dim, n_units, n_units)*init_std)
        self.W_f = nn.Parameter(torch.randn(input_dim, n_units, n_units)*init_std)
        self.W_o = nn.Parameter(torch.randn(input_dim, n_units, n_units)*init_std)
        self.b_j = nn.Parameter(torch.randn(input_dim, n_units)*init_std)
        self.b_i = nn.Parameter(torch.randn(input_dim, n_units)*init_std)
        self.b_f = nn.Parameter(torch.randn(input_dim, n_units)*init_std)
        self.b_o = nn.Parameter(torch.randn(input_dim, n_units)*init_std)
        self.dropout = nn.Dropout(p=p) # dropout
        self.F_alpha_n = nn.Parameter(torch.randn(input_dim, n_units, n_units)*init_std)
        self.F_alpha_n_b = nn.Parameter(torch.randn(input_dim, n_units)*init_std)
        self.F_alpha_1 = nn.Linear(n_units, 1)
        self.F_beta_n = nn.Parameter(torch.randn(input_dim, 2*n_units, 2*n_units)*init_std)
        self.F_beta_n_b = nn.Parameter(torch.randn(input_dim, 2*n_units)*init_std)
        self.F_beta_d = nn.Linear(2*n_units, n_units) # dropout will be applied
        self.F_beta_1 = nn.Linear(n_units, 1) # 2*n_units -> n_units
        self.Phi_d = nn.Linear(2*n_units, n_units) # dropout will be applied
        self.Phi = nn.Linear(n_units, output_dim) # 2*n_units -> n_units
        self.n_units = n_units
        self.input_dim = input_dim
    
    @torch.jit.script_method
    def forward(self, x):
        h_tilda_t = torch.zeros(x.shape[0], self.input_dim, self.n_units).cuda()
        c_tilda_t = torch.zeros(x.shape[0], self.input_dim, self.n_units).cuda()
        outputs = torch.jit.annotate(List[Tensor], [])
        for t in range(x.shape[1]):
            # eq 1
            j_tilda_t = torch.tanh(torch.einsum("bij,ijk->bik", h_tilda_t, self.W_j) + \
                                   torch.einsum("bij,jik->bjk", x[:,t,:].unsqueeze(1), self.U_j) + self.b_j)
            # eq 5
            i_tilda_t = torch.sigmoid(torch.einsum("bij,ijk->bik", h_tilda_t, self.W_i) + \
                                torch.einsum("bij,jik->bjk", x[:,t,:].unsqueeze(1), self.U_i) + self.b_i)
            f_tilda_t = torch.sigmoid(torch.einsum("bij,ijk->bik", h_tilda_t, self.W_f) + \
                                torch.einsum("bij,jik->bjk", x[:,t,:].unsqueeze(1), self.U_f) + self.b_f)
            o_tilda_t = torch.sigmoid(torch.einsum("bij,ijk->bik", h_tilda_t, self.W_o) + \
                                torch.einsum("bij,jik->bjk", x[:,t,:].unsqueeze(1), self.U_o) + self.b_o)
            # eq 6
            c_tilda_t = c_tilda_t*f_tilda_t + i_tilda_t*j_tilda_t
            # eq 7
            h_tilda_t = (o_tilda_t*torch.tanh(c_tilda_t))
            outputs += [h_tilda_t]
        outputs = torch.stack(outputs)
        outputs = outputs.permute(1, 0, 2, 3)
        # eq 8
        alphas = self.F_alpha_1(torch.tanh(torch.einsum("btij,ijk->btik", outputs, self.F_alpha_n) +self.F_alpha_n_b))
        alphas = torch.exp(alphas)
        alphas = alphas/torch.sum(alphas, dim=1, keepdim=True)
        g_n = torch.sum(alphas*outputs, dim=1)
        hg = torch.cat([g_n, h_tilda_t], dim=2)
        hg2 = self.Phi_d(hg) # hg will be used again later
        hg_dropout = self.dropout(hg2) 
        mu = self.Phi(hg_dropout)
        betas = self.F_beta_d(torch.tanh(torch.einsum("bij, ijk->bik", hg, self.F_beta_n) + self.F_beta_n_b))
        betas = self.dropout(betas) 
        betas = self.F_beta_1(betas)
        betas = torch.exp(betas)
        betas = betas/torch.sum(betas, dim=1, keepdim=True)
        mean = torch.sum(betas*mu, dim=1)
        
        return mean, alphas, betas

    
class IMVFullLSTM_dropout(torch.jit.ScriptModule):
    __constants__ = ["n_units", "input_dim"]
    def __init__(self, input_dim, output_dim, n_units, init_std=0.02, p=0.1):
        super().__init__()
        self.U_j = nn.Parameter(torch.randn(input_dim, 1, n_units)*init_std)
        self.W_j = nn.Parameter(torch.randn(input_dim, n_units, n_units)*init_std)
        self.b_j = nn.Parameter(torch.randn(input_dim, n_units)*init_std)
        self.W_i = nn.Linear(input_dim*(n_units+1), input_dim*n_units)
        self.W_f = nn.Linear(input_dim*(n_units+1), input_dim*n_units)
        self.W_o = nn.Linear(input_dim*(n_units+1), input_dim*n_units)
        self.dropout = nn.Dropout(p=p) # dropout
        self.F_alpha_n = nn.Parameter(torch.randn(input_dim, n_units, n_units)*init_std)
        self.F_alpha_n_b = nn.Parameter(torch.randn(input_dim, n_units)*init_std)
        self.F_alpha_1 = nn.Linear(n_units, 1)
        self.F_beta_n = nn.Parameter(torch.randn(input_dim, 2*n_units, 2*n_units)*init_std)
        self.F_beta_n_b = nn.Parameter(torch.randn(input_dim, 2*n_units)*init_std)
        self.F_beta_d = nn.Linear(2*n_units, n_units) # dropout will be applied
        self.F_beta_1 = nn.Linear(n_units, 1) # 2*n_units -> n_units
        self.Phi_d = nn.Linear(2*n_units, n_units) # dropout will be applied
        self.Phi = nn.Linear(n_units, output_dim) # 2*n_units -> n_units
        self.n_units = n_units
        self.input_dim = input_dim
        
    @torch.jit.script_method
    def forward(self, x):
        h_tilda_t = torch.zeros(x.shape[0], self.input_dim, self.n_units).cuda()
        c_t = torch.zeros(x.shape[0], self.input_dim*self.n_units).cuda()
        outputs = torch.jit.annotate(List[Tensor], [])
        for t in range(x.shape[1]):
            # eq 1
            j_tilda_t = torch.tanh(torch.einsum("bij,ijk->bik", h_tilda_t, self.W_j) + \
                                   torch.einsum("bij,jik->bjk", x[:,t,:].unsqueeze(1), self.U_j) + self.b_j)
            inp =  torch.cat([x[:, t, :], h_tilda_t.view(h_tilda_t.shape[0], -1)], dim=1)
            # eq 2
            i_t = torch.sigmoid(self.W_i(inp))
            f_t = torch.sigmoid(self.W_f(inp))
            o_t = torch.sigmoid(self.W_o(inp))
            # eq 3
            c_t = c_t*f_t + i_t*j_tilda_t.view(j_tilda_t.shape[0], -1)
            # eq 4
            h_tilda_t = (o_t*torch.tanh(c_t)).view(h_tilda_t.shape[0], self.input_dim, self.n_units)
            outputs += [h_tilda_t]
        outputs = torch.stack(outputs)
        outputs = outputs.permute(1, 0, 2, 3)
        # eq 8
        alphas = self.F_alpha_1(torch.tanh(torch.einsum("btij,ijk->btik", outputs, self.F_alpha_n) +self.F_alpha_n_b))
        alphas = torch.exp(alphas)
        alphas = alphas/torch.sum(alphas, dim=1, keepdim=True)
        g_n = torch.sum(alphas*outputs, dim=1)
        hg = torch.cat([g_n, h_tilda_t], dim=2)
        hg2 = self.Phi_d(hg) # hg will be used again later
        hg_dropout = self.dropout(hg2) 
        mu = self.Phi(hg_dropout)
        betas = self.F_beta_d(torch.tanh(torch.einsum("bij, ijk->bik", hg, self.F_beta_n) + self.F_beta_n_b))
        betas = self.dropout(betas) 
        betas = self.F_beta_1(betas)
        betas = torch.exp(betas)
        betas = betas/torch.sum(betas, dim=1, keepdim=True)
        mean = torch.sum(betas*mu, dim=1)
        return mean, alphas, betas