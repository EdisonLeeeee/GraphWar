import torch
import torch.nn.functional as F
import scipy.sparse as sp
from copy import copy

from torch_geometric.data import Data
from torch_geometric.transforms import BaseTransform
from torch_geometric.utils import degree, to_scipy_sparse_matrix, from_scipy_sparse_matrix


class JaccardPurification(BaseTransform):

    def __init__(self, threshold: float = 0., allow_singleton: bool = False):
        # TODO: add percentage purification
        self.threshold = threshold
        self.allow_singleton = allow_singleton
        self.removed_edges = None

    def __call__(self, data: Data, inplace: bool = True) -> Data:
        if not inplace:
            data = copy(data)

        row, col = data.edge_index
        A = data.x[row]
        B = data.x[col]
        score = jaccard_similarity(A, B)
        deg = degree(row, num_nodes=data.num_nodes)

        if self.allow_singleton:
            mask = score <= self.threshold
        else:
            mask = torch.logical_and(
                score <= self.threshold, deg[col] > 1)

        self.removed_edges = data.edge_index[:, mask]
        data.edge_index = data.edge_index[:, ~mask]
        return data

    def __repr__(self) -> str:
        return f'{self.__class__.__name__}(threshold={self.threshold}, allow_singleton={self.allow_singleton})'


class CosinePurification(BaseTransform):

    def __init__(self, threshold: float = 0., allow_singleton: bool = False):
        # TODO: add percentage purification
        self.threshold = threshold
        self.allow_singleton = allow_singleton
        self.removed_edges = None

    def __call__(self, data: Data, inplace: bool = True) -> Data:
        if not inplace:
            data = copy(data)

        row, col = data.edge_index
        A = data.x[row]
        B = data.x[col]
        score = F.cosine_similarity(A, B)
        deg = degree(row, num_nodes=data.num_nodes)

        if self.allow_singleton:
            mask = score <= self.threshold
        else:
            mask = torch.logical_and(
                score <= self.threshold, deg[col] > 1)

        self.removed_edges = data.edge_index[:, mask]
        data.edge_index = data.edge_index[:, ~mask]
        return data

    def __repr__(self) -> str:
        return f'{self.__class__.__name__}(threshold={self.threshold}, allow_singleton={self.allow_singleton})'


class SVDPurification(BaseTransform):

    def __init__(self, K: int = 50, threshold: float = 0.01, binaryzation: bool = False):
        # TODO: add percentage purification
        super().__init__()
        self.K = K
        self.threshold = threshold
        self.binaryzation = binaryzation

    def __call__(self, data: Data, inplace: bool = True) -> Data:
        if not inplace:
            data = copy(data)

        device = data.edge_index.device
        adj_matrix = to_scipy_sparse_matrix(data.edge_index, data.edge_weight,
                                            num_nodes=data.num_nodes).tocsr()
        adj_matrix = svd(adj_matrix, K=self.K,
                         threshold=self.threshold,
                         binaryzation=self.binaryzation)
        edge_index, edge_weight = from_scipy_sparse_matrix(
            adj_matrix)
        data.edge_index, data.edge_weight = edge_index.to(
            device), edge_weight.to(device)

        return data

    def __repr__(self) -> str:
        return f'{self.__class__.__name__}(K={self.K}, threshold={self.threshold}, allow_singleton={self.allow_singleton})'


def jaccard_similarity(A: torch.Tensor, B: torch.Tensor) -> torch.Tensor:
    intersection = torch.count_nonzero(A * B, axis=1)
    J = intersection * 1.0 / (torch.count_nonzero(A, dim=1) +
                              torch.count_nonzero(B, dim=1) - intersection + 1e-7)
    return J


def svd(adj_matrix: sp.csr_matrix, K: int = 50,
        threshold: float = 0.01, binaryzation: bool = False) -> sp.csr_matrix:

    adj_matrix = adj_matrix.asfptype()

    U, S, V = sp.linalg.svds(adj_matrix, k=K)
    adj_matrix = (U * S) @ V

    if threshold is not None:
        # sparsification
        adj_matrix[adj_matrix <= threshold] = 0.

    adj_matrix = sp.csr_matrix(adj_matrix)

    if binaryzation:
        # TODO
        adj_matrix.data[adj_matrix.data > 0] = 1.0

    return adj_matrix
