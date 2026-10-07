from heteroes.noise.contracts import ParameterNoiseAddress, DEFAULT_CHUNK_ELEMENTS
from heteroes.noise.engine import iter_parameter_noise_chunks
from heteroes.model.schema import ParameterSchema, resolve_tensors
from heteroes.es.checks import _check_param_sigma, SUPPORT_DTYPE
import math
import torch 
import numpy as np     
    
# The noise of consecutive chunks is joined into pieces of about this many elements before it goes to the device: the arithmetic is
# elementwise, so the bits do not depend on the piece size (checked by the tests and by the hash of the real model), but one launch of
# each operation per piece instead of per chunk of 2**18 elements saves most of the Python and launch overhead.
BATCH_ELEMENTS = 2**22

# for param float 16 only
# perturb inplace, (not copy to new tensor)
def perturb_parameter_(param: torch.Tensor, param_noise_address: ParameterNoiseAddress, sigma: float) -> None: 
    """
    Perturb one parameter tensor in place:
        param <- fp16( fp32(param) + fp32(sigma) * fp32(eps) )

    - eps comes from the canonical noise engine, so every machine gets the same bits.
    - The multiply and the add are two separate operations on purpose (contract O2 = c).
      Do NOT replace them with add_(eps, alpha=sigma): that fuses them into one rounding
      step and gives a different result on the CPU than on the GPU.
    - Works one chunk at a time, so memory stays small.

    Raises TypeError if param is not FP16, ValueError if it is not contiguous.
    """
    # check param and sigma 
    _check_param_sigma(param, sigma)

    # convert sigma to float 32 (convert to numpy float 32 then convert to python)
    sigma_float_32 = float(np.float32(sigma))
            

    # disable gradient 
    with torch.no_grad(): 
        flat_param = param.view(-1) # not copy to new tensor 
        numel = flat_param.numel()
        pending, pending_elements, first = [], 0, 0

        def apply_pending():
            nonlocal pending, pending_elements
            noise_numpy_f16 = pending[0] if len(pending) == 1 else np.concatenate(pending)
            param_chunk = flat_param[first : first + noise_numpy_f16.size]
            eps = torch.from_numpy(noise_numpy_f16).to(param.device)

            scaled = eps.to(torch.float32) * sigma_float_32
            perturbed = param_chunk.to(torch.float32) + scaled
            perturbed = perturbed.to(SUPPORT_DTYPE) # cast to orginal dtype 
            param_chunk.copy_(perturbed)
            pending, pending_elements = [], 0

        for _, start, noise_numpy_f16 in iter_parameter_noise_chunks(param_noise_address, numel):
            if not pending:
                first = start
            pending.append(noise_numpy_f16)
            pending_elements += noise_numpy_f16.size
            if pending_elements >= BATCH_ELEMENTS:
                apply_pending()
        if pending:
            apply_pending()

# perturb whole model (inplace ) 
def perturb_model_(model: torch.nn.Module, schema: ParameterSchema, candidate_seed: int, sigma: float, chunk_elements: int = DEFAULT_CHUNK_ELEMENTS) -> None: 
    """
    Perturb every tensor of the model in place: theta' = theta + sigma * eps, one noise stream
    per schema entry (see perturb_parameter_ for the exact arithmetic).

    Args:
        schema: the layout the model must match. It comes from the candidate manifest, never
            from the model itself, otherwise "does the model match?" would compare it with itself.
        candidate_seed, chunk_elements: part of the noise address. sigma is not (it belongs to
            the candidate, not to the noise).

    Everything that can be checked is checked BEFORE the first tensor is touched: schema match,
    dtype, contiguity and sigma. If any check fails nothing has been modified.

    What this does NOT guarantee: a failure while perturbing (for example CUDA out of memory
    at tensor 200) leaves tensors 1..199 perturbed and the rest untouched. The caller must then
    restore the model from its snapshot and treat the worker as suspect. That is why restore
    exists and why it must be bitwise exact.

    A tied tensor appears once in the schema, so it is perturbed once.

    Raises:
        SchemaMismatchError: the model does not match the schema.
        TypeError / ValueError: a tensor is not contiguous FP16, or sigma is NaN/Inf.
    """

    # resolve tensor 
    tensors = resolve_tensors(model, schema)

    # check tensor and sigma 
    for tensor in tensors: 
        _check_param_sigma(tensor, sigma)
  
    # perturb
    schema_hash = schema.hash
    for entry, tensor in zip(schema.entries, tensors, strict=True): 
        param_noise_address = ParameterNoiseAddress(
            candidate_seed=candidate_seed,
            schema_hash=schema_hash, 
            parameter_index=entry.index,
            chunk_elements=chunk_elements, 
        )

        perturb_parameter_(tensor, param_noise_address, sigma)
    