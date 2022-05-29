import torch
from torch import nn
from torch import Tensor
from torch_geometric.nn.conv.gcn_conv import gcn_norm
from torch_geometric.nn.dense.linear import Linear
from torch_geometric.nn.inits import zeros
from torch_geometric.typing import Adj, OptTensor
from torch_sparse import SparseTensor

from graphwar import is_edge_index
from graphwar.functional import spmm

def dense_gcn_norm(adj: Tensor, improved: bool = False, 
                   add_self_loops: bool = True, rate: float = -0.5):
    fill_value = 2. if improved else 1.
    if add_self_loops:
        adj = adj + torch.diag(adj.new_full((adj.size(0),), fill_value))
    deg = adj.sum(dim=1)
    deg_inv_sqrt = deg.pow_(rate)
    deg_inv_sqrt.masked_fill_(deg_inv_sqrt == float('inf'), 0.)    
    norm_src = deg_inv_sqrt.view(1, -1)
    norm_dst = deg_inv_sqrt.view(-1, 1)
    adj = norm_src * adj * norm_dst
    return adj


class GCNConv(nn.Module):
    def __init__(self, in_channels: int, out_channels: int,
                 improved: bool = False, cached: bool = False,
                 add_self_loops: bool = True, normalize: bool = True,
                 bias: bool = True):

        super().__init__()

        self.in_channels = in_channels
        self.out_channels = out_channels
        self.improved = improved
        self.cached = cached # NOTE: unused now
        self.add_self_loops = add_self_loops
        self.normalize = normalize

        self.lin = Linear(in_channels, out_channels, bias=False,
                          weight_initializer='glorot')

        if bias:
            self.bias = nn.Parameter(torch.Tensor(out_channels))
        else:
            self.register_parameter('bias', None)

        self.reset_parameters()

    def reset_parameters(self):
        self.lin.reset_parameters()
        zeros(self.bias)
        
    def forward(self, x: Tensor, edge_index: Adj, 
                edge_weight: OptTensor = None) -> Tensor:
        
        x = self.lin(x)
        is_edge_like = is_edge_index(edge_index)
        
        if self.normalize:
            if is_edge_like:
                edge_index, edge_weight = gcn_norm(edge_index, edge_weight, x.size(0),
                                                   self.improved, self.add_self_loops, dtype=x.dtype)
            elif isinstance(edge_index, SparseTensor):
                edge_index = gcn_norm(edge_index, x.size(0), 
                               improved=self.improved, 
                               add_self_loops=self.add_self_loops, dtype=x.dtype)
                
            else:
                # N by N dense adjacency matrix
                edge_index = dense_gcn_norm(edge_index, improved=self.improved, 
                                     add_self_loops=self.add_self_loops)

        if is_edge_like:
            out = spmm(x, edge_index, edge_weight)
        else:
            out = edge_index @ x

        if self.bias is not None:
            out += self.bias

        return out

    def __repr__(self) -> str:
        return (f'{self.__class__.__name__}({self.in_channels}, '
                f'{self.out_channels})')    