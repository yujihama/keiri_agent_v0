"""Control Blocks - 監査・内部統制ブロック群

監査・内部統制業務に特化したブロック群を提供します。
承認統制、職務分掌、サンプリングなどの専門的な処理を標準化・自動化します。
"""

from .approval import ApprovalBlock
from .sod_check import SodCheckBlock
from .sampling import SamplingBlock

__all__ = [
    'ApprovalBlock',
    'SodCheckBlock', 
    'SamplingBlock'
]