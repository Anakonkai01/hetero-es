import torch 
import math
SUPPORT_DTYPE = torch.float16



def _check_param(param: torch.Tensor) -> None: 
    if not param.is_contiguous(): 
        # torch.reshape would silently write into a copy and leave param unchanged
        raise ValueError("param must be contiguous")
    if param.dtype != SUPPORT_DTYPE: 
        raise TypeError(f"param must be {SUPPORT_DTYPE}, got {param.dtype}")

def _check_sigma(sigma: float) -> None: 
    if not math.isfinite(sigma): 
        raise ValueError("sigma must not be Nan/Inf")
    
def _check_param_sigma(param: torch.Tensor, sigma: float) -> None: 
    _check_param(param)
    _check_sigma(sigma)
    