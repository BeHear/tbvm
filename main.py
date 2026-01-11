import torch
import bitsandbytes as bnb

print(f"CUDA доступна: {torch.cuda.is_available()}")
print(f"Количество GPU: {torch.cuda.device_count()}")
# Если это выведет True, значит 4-битное квантование будет работать