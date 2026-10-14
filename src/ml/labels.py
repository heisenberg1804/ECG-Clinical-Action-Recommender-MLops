"""PTB-XL diagnostic superclasses, in model output order.

Kept dependency-free so serving can import it without the training stack.
"""

SUPERCLASSES = ['NORM', 'MI', 'STTC', 'CD', 'HYP']
