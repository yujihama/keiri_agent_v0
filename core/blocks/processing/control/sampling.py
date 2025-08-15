"""サンプリングブロック

統計的・属性・リスクベースサンプリングの実行を行います。
統計的サンプリング、リスクベースサンプリング、系統的サンプリング、ランダムサンプリングなどの手法を提供します。
"""

from __future__ import annotations
from typing import Dict, Any, List, Optional
import random
import math
import json
import os
import uuid
from datetime import datetime, timedelta
from pydantic import BaseModel, Field

from core.blocks.base import ProcessingBlock, BlockContext
from core.errors import BlockExecutionError
from core.evidence.vault import EvidenceVault
from core.evidence.metadata import EvidenceMetadata, EvidenceType


class PopulationItem(BaseModel):
    """母集団アイテム"""
    item_id: str
    value: float
    risk_score: Optional[float] = 0.0
    attributes: Dict[str, Any] = {}


class PopulationData(BaseModel):
    """母集団データ"""
    data_source: str
    total_items: int
    total_value: Optional[float] = None
    items: List[PopulationItem]


class StratificationConfig(BaseModel):
    """層化設定"""
    enabled: bool = False
    strata_field: Optional[str] = None
    strata_weights: Dict[str, float] = {}


class RiskCriteria(BaseModel):
    """リスク基準"""
    high_risk_threshold: float = 0.7
    medium_risk_threshold: float = 0.3
    high_risk_percentage: float = 0.8


class SamplingParameters(BaseModel):
    """サンプリングパラメータ"""
    method: str  # statistical, attribute, risk_based, systematic, random
    confidence_level: Optional[float] = 0.95
    tolerable_error_rate: Optional[float] = 0.05
    expected_error_rate: Optional[float] = 0.02
    sample_size: Optional[int] = None
    stratification: StratificationConfig = StratificationConfig()
    risk_criteria: RiskCriteria = RiskCriteria()


class SelectedItem(BaseModel):
    """選択されたアイテム"""
    item_id: str
    value: float
    risk_score: float
    selection_reason: str
    stratum: Optional[str] = None


class SamplingBlock(ProcessingBlock):
    """サンプリングブロック"""
    
    def execute(self, inputs: Dict[str, Any], context: BlockContext) -> Dict[str, Any]:
        """サンプリングの実行"""
        try:
            # 入力データの検証
            population = PopulationData(**inputs['population_data'])
            parameters = SamplingParameters(**inputs['sampling_parameters'])
            
            # サンプリング実行
            if parameters.method == 'statistical':
                selected_items, sampling_result = self._statistical_sampling(population, parameters)
            elif parameters.method == 'attribute':
                selected_items, sampling_result = self._attribute_sampling(population, parameters)
            elif parameters.method == 'risk_based':
                selected_items, sampling_result = self._risk_based_sampling(population, parameters)
            elif parameters.method == 'systematic':
                selected_items, sampling_result = self._systematic_sampling(population, parameters)
            elif parameters.method == 'random':
                selected_items, sampling_result = self._random_sampling(population, parameters)
            else:
                raise ValueError(f"未対応のサンプリング手法: {parameters.method}")
            
            # 統計計算
            sampling_statistics = self._calculate_statistics(selected_items, population)
            
            # 証跡ファイル生成
            evidence_files = self._generate_evidence_files(
                population, parameters, selected_items, sampling_result, context
            )
            
            return {
                'sampling_result': sampling_result,
                'selected_items': [item.dict() for item in selected_items],
                'sampling_statistics': sampling_statistics,
                'evidence_files': evidence_files
            }
            
        except Exception as e:
            raise BlockExecutionError(f"サンプリング処理でエラーが発生しました: {str(e)}")
    
    def _statistical_sampling(self, population: PopulationData, 
                            parameters: SamplingParameters) -> tuple[List[SelectedItem], Dict[str, Any]]:
        """統計的サンプリング"""
        # サンプルサイズ計算
        if parameters.sample_size:
            sample_size = parameters.sample_size
        else:
            sample_size = self._calculate_statistical_sample_size(
                population.total_items,
                parameters.confidence_level,
                parameters.tolerable_error_rate,
                parameters.expected_error_rate
            )
        
        # ランダムサンプリング実行
        selected_indices = random.sample(range(len(population.items)), min(sample_size, len(population.items)))
        selected_items = []
        
        for idx in selected_indices:
            item = population.items[idx]
            selected_items.append(SelectedItem(
                item_id=item.item_id,
                value=item.value,
                risk_score=item.risk_score,
                selection_reason='統計的ランダムサンプリング'
            ))
        
        sampling_result = {
            'method_used': 'statistical',
            'sample_size': len(selected_items),
            'population_size': population.total_items,
            'sampling_ratio': len(selected_items) / population.total_items,
            'confidence_level': parameters.confidence_level,
            'margin_of_error': self._calculate_margin_of_error(len(selected_items), parameters.confidence_level)
        }
        
        return selected_items, sampling_result
    
    def _attribute_sampling(self, population: PopulationData,
                          parameters: SamplingParameters) -> tuple[List[SelectedItem], Dict[str, Any]]:
        """属性サンプリング"""
        # 属性サンプリングは統計的サンプリングと同様だが、属性の存在/非存在に焦点
        sample_size = parameters.sample_size or self._calculate_statistical_sample_size(
            population.total_items,
            parameters.confidence_level,
            parameters.tolerable_error_rate,
            parameters.expected_error_rate
        )
        
        selected_indices = random.sample(range(len(population.items)), min(sample_size, len(population.items)))
        selected_items = []
        
        for idx in selected_indices:
            item = population.items[idx]
            selected_items.append(SelectedItem(
                item_id=item.item_id,
                value=item.value,
                risk_score=item.risk_score,
                selection_reason='属性サンプリング'
            ))
        
        sampling_result = {
            'method_used': 'attribute',
            'sample_size': len(selected_items),
            'population_size': population.total_items,
            'sampling_ratio': len(selected_items) / population.total_items,
            'confidence_level': parameters.confidence_level,
            'margin_of_error': self._calculate_margin_of_error(len(selected_items), parameters.confidence_level)
        }
        
        return selected_items, sampling_result
    
    def _risk_based_sampling(self, population: PopulationData,
                           parameters: SamplingParameters) -> tuple[List[SelectedItem], Dict[str, Any]]:
        """リスクベースサンプリング"""
        # リスクレベル別分類
        high_risk_items = [item for item in population.items 
                          if item.risk_score >= parameters.risk_criteria.high_risk_threshold]
        medium_risk_items = [item for item in population.items 
                           if parameters.risk_criteria.medium_risk_threshold <= item.risk_score < parameters.risk_criteria.high_risk_threshold]
        low_risk_items = [item for item in population.items 
                         if item.risk_score < parameters.risk_criteria.medium_risk_threshold]
        
        selected_items = []
        
        # 高リスクアイテムの選択
        high_risk_sample_size = int(len(high_risk_items) * parameters.risk_criteria.high_risk_percentage)
        if high_risk_sample_size > 0 and high_risk_items:
            high_risk_selected = random.sample(high_risk_items, min(high_risk_sample_size, len(high_risk_items)))
            for item in high_risk_selected:
                selected_items.append(SelectedItem(
                    item_id=item.item_id,
                    value=item.value,
                    risk_score=item.risk_score,
                    selection_reason='高リスクアイテム'
                ))
        
        # 残りのサンプルサイズ計算
        remaining_sample_size = (parameters.sample_size or 50) - len(selected_items)
        if remaining_sample_size > 0:
            remaining_items = medium_risk_items + low_risk_items
            if remaining_items:
                additional_selected = random.sample(remaining_items, min(remaining_sample_size, len(remaining_items)))
                for item in additional_selected:
                    risk_level = 'medium' if item.risk_score >= parameters.risk_criteria.medium_risk_threshold else 'low'
                    selected_items.append(SelectedItem(
                        item_id=item.item_id,
                        value=item.value,
                        risk_score=item.risk_score,
                        selection_reason=f'{risk_level}リスクアイテム'
                    ))
        
        sampling_result = {
            'method_used': 'risk_based',
            'sample_size': len(selected_items),
            'population_size': population.total_items,
            'sampling_ratio': len(selected_items) / population.total_items,
            'confidence_level': parameters.confidence_level or 0.95,
            'margin_of_error': self._calculate_margin_of_error(len(selected_items), parameters.confidence_level or 0.95)
        }
        
        return selected_items, sampling_result
    
    def _systematic_sampling(self, population: PopulationData,
                           parameters: SamplingParameters) -> tuple[List[SelectedItem], Dict[str, Any]]:
        """系統的サンプリング"""
        sample_size = parameters.sample_size or min(50, len(population.items))
        
        if sample_size >= len(population.items):
            # 全数選択
            selected_items = [
                SelectedItem(
                    item_id=item.item_id,
                    value=item.value,
                    risk_score=item.risk_score,
                    selection_reason='系統的サンプリング（全数）'
                )
                for item in population.items
            ]
        else:
            # 系統的サンプリング
            interval = len(population.items) // sample_size
            start = random.randint(0, interval - 1) if interval > 1 else 0
            
            selected_items = []
            for i in range(sample_size):
                idx = (start + i * interval) % len(population.items)
                item = population.items[idx]
                selected_items.append(SelectedItem(
                    item_id=item.item_id,
                    value=item.value,
                    risk_score=item.risk_score,
                    selection_reason=f'系統的サンプリング（間隔:{interval}）'
                ))
        
        sampling_result = {
            'method_used': 'systematic',
            'sample_size': len(selected_items),
            'population_size': population.total_items,
            'sampling_ratio': len(selected_items) / population.total_items,
            'confidence_level': parameters.confidence_level or 0.95,
            'margin_of_error': self._calculate_margin_of_error(len(selected_items), parameters.confidence_level or 0.95)
        }
        
        return selected_items, sampling_result
    
    def _random_sampling(self, population: PopulationData,
                        parameters: SamplingParameters) -> tuple[List[SelectedItem], Dict[str, Any]]:
        """ランダムサンプリング"""
        sample_size = parameters.sample_size or min(50, len(population.items))
        
        selected_indices = random.sample(range(len(population.items)), min(sample_size, len(population.items)))
        selected_items = []
        
        for idx in selected_indices:
            item = population.items[idx]
            selected_items.append(SelectedItem(
                item_id=item.item_id,
                value=item.value,
                risk_score=item.risk_score,
                selection_reason='ランダムサンプリング'
            ))
        
        sampling_result = {
            'method_used': 'random',
            'sample_size': len(selected_items),
            'population_size': population.total_items,
            'sampling_ratio': len(selected_items) / population.total_items,
            'confidence_level': parameters.confidence_level or 0.95,
            'margin_of_error': self._calculate_margin_of_error(len(selected_items), parameters.confidence_level or 0.95)
        }
        
        return selected_items, sampling_result
    
    def _calculate_statistical_sample_size(self, population_size: int, confidence_level: float,
                                         tolerable_error_rate: float, expected_error_rate: float) -> int:
        """統計的サンプルサイズ計算"""
        # Z値の計算
        z_values = {0.90: 1.645, 0.95: 1.96, 0.99: 2.576}
        z = z_values.get(confidence_level, 1.96)
        
        # サンプルサイズ計算（属性サンプリング用）
        numerator = (z ** 2) * expected_error_rate * (1 - expected_error_rate)
        denominator = tolerable_error_rate ** 2
        
        sample_size = math.ceil(numerator / denominator)
        
        # 有限母集団修正
        if population_size < 10000:
            sample_size = math.ceil(sample_size / (1 + (sample_size - 1) / population_size))
        
        return min(sample_size, population_size)
    
    def _calculate_margin_of_error(self, sample_size: int, confidence_level: float) -> float:
        """誤差範囲計算"""
        z_values = {0.90: 1.645, 0.95: 1.96, 0.99: 2.576}
        z = z_values.get(confidence_level, 1.96)
        
        if sample_size <= 0:
            return 1.0
        
        return z / math.sqrt(sample_size)
    
    def _calculate_statistics(self, selected_items: List[SelectedItem], 
                            population: PopulationData) -> Dict[str, Any]:
        """サンプリング統計計算"""
        if not selected_items:
            return {
                'total_sample_value': 0,
                'average_item_value': 0,
                'value_coverage_ratio': 0,
                'risk_distribution': {
                    'high_risk_count': 0,
                    'medium_risk_count': 0,
                    'low_risk_count': 0
                }
            }
        
        total_sample_value = sum(item.value for item in selected_items)
        average_item_value = total_sample_value / len(selected_items)
        
        # リスク分布
        high_risk_count = sum(1 for item in selected_items if item.risk_score >= 0.7)
        medium_risk_count = sum(1 for item in selected_items if 0.3 <= item.risk_score < 0.7)
        low_risk_count = sum(1 for item in selected_items if item.risk_score < 0.3)
        
        # 金額カバー率
        population_total_value = population.total_value or sum(item.value for item in population.items)
        value_coverage_ratio = total_sample_value / population_total_value if population_total_value > 0 else 0
        
        return {
            'total_sample_value': total_sample_value,
            'average_item_value': average_item_value,
            'value_coverage_ratio': value_coverage_ratio,
            'risk_distribution': {
                'high_risk_count': high_risk_count,
                'medium_risk_count': medium_risk_count,
                'low_risk_count': low_risk_count
            }
        }
    
    def _generate_evidence_files(self, population: PopulationData, parameters: SamplingParameters,
                               selected_items: List[SelectedItem], sampling_result: Dict[str, Any],
                               context: BlockContext) -> List[str]:
        """証跡ファイルの生成"""
        evidence_files = []
        
        try:
            # Evidence Vaultの取得
            evidence_vault = getattr(context, 'evidence_vault', None)
            if not evidence_vault:
                # Evidence Vaultが設定されていない場合は従来の方式でファイル保存
                evidence_files = self._generate_legacy_evidence_files(population, parameters, selected_items, sampling_result, context)
            else:
                # Evidence Vaultを使用した証跡保存
                evidence_files = self._generate_vault_evidence_files(population, parameters, selected_items, sampling_result, context, evidence_vault)
        
        except Exception as e:
            # 証跡生成失敗時は警告ログを出力するが処理は継続
            import logging
            logging.warning(f"証跡ファイル生成でエラーが発生しました: {str(e)}")
            evidence_files = []
        
        return evidence_files
    
    def _generate_legacy_evidence_files(self, population: PopulationData, parameters: SamplingParameters,
                                      selected_items: List[SelectedItem], sampling_result: Dict[str, Any],
                                      context: BlockContext) -> List[str]:
        """従来方式での証跡ファイル生成"""
        evidence_files = []
        
        if context.workspace:
            # サンプリング結果ファイル
            result_file = os.path.join(context.workspace, f"sampling_result_{context.run_id}.json")
            with open(result_file, 'w', encoding='utf-8') as f:
                result_data = {
                    'sampling_result': sampling_result,
                    'selected_items': [item.dict() for item in selected_items],
                    'parameters': parameters.dict(),
                    'population_summary': {
                        'data_source': population.data_source,
                        'total_items': population.total_items,
                        'total_value': population.total_value
                    }
                }
                json.dump(result_data, f, ensure_ascii=False, indent=2, default=str)
            evidence_files.append(result_file)
            
            # サンプリングパラメータファイル
            params_file = os.path.join(context.workspace, f"sampling_parameters_{context.run_id}.json")
            with open(params_file, 'w', encoding='utf-8') as f:
                json.dump(parameters.dict(), f, ensure_ascii=False, indent=2)
            evidence_files.append(params_file)
        
        return evidence_files
    
    def _generate_vault_evidence_files(self, population: PopulationData, parameters: SamplingParameters,
                                     selected_items: List[SelectedItem], sampling_result: Dict[str, Any],
                                     context: BlockContext, evidence_vault: EvidenceVault) -> List[str]:
        """Evidence Vaultを使用した証跡保存"""
        evidence_files = []
        
        # サンプリング結果の証跡保存
        result_evidence_id = f"sampling_result_{uuid.uuid4().hex[:8]}"
        result_metadata = EvidenceMetadata(
            evidence_id=result_evidence_id,
            evidence_type=EvidenceType.CONTROL_RESULT,
            block_id=self.__class__.__name__,
            run_id=context.run_id,
            timestamp=datetime.now(),
            file_path=f"evidence/control/{context.run_id}/{result_evidence_id}.json",
            file_hash="",
            file_size=0,
            retention_until=datetime.now() + timedelta(days=2555),
            tags=['sampling_control', 'result', parameters.method],
            department=getattr(context, 'department', None),
            risk_level='medium'
        )
        
        result_data = {
            'sampling_result': sampling_result,
            'selected_items': [item.dict() for item in selected_items],
            'sampling_statistics': self._calculate_statistics(selected_items, population),
            'execution_timestamp': datetime.now().isoformat()
        }
        
        stored_id = evidence_vault.store_evidence(result_data, result_metadata)
        evidence_files.append(f"vault:{stored_id}")
        
        # サンプリングパラメータの証跡保存
        params_evidence_id = f"sampling_params_{uuid.uuid4().hex[:8]}"
        params_metadata = EvidenceMetadata(
            evidence_id=params_evidence_id,
            evidence_type=EvidenceType.CONTROL_RESULT,
            block_id=self.__class__.__name__,
            run_id=context.run_id,
            timestamp=datetime.now(),
            file_path=f"evidence/control/{context.run_id}/{params_evidence_id}.json",
            file_hash="",
            file_size=0,
            retention_until=datetime.now() + timedelta(days=2555),
            tags=['sampling_control', 'parameters', parameters.method],
            related_evidence=[result_evidence_id]
        )
        
        params_data = {
            'parameters': parameters.dict(),
            'population_summary': {
                'data_source': population.data_source,
                'total_items': population.total_items,
                'total_value': population.total_value
            },
            'method_justification': self._get_method_justification(parameters.method)
        }
        
        stored_id = evidence_vault.store_evidence(params_data, params_metadata)
        evidence_files.append(f"vault:{stored_id}")
        
        return evidence_files
    
    def _get_method_justification(self, method: str) -> str:
        """サンプリング手法の選択理由"""
        justifications = {
            'statistical': '統計的有意性を確保するための確率論的サンプリング',
            'attribute': '特定属性の存在/非存在を検証するためのサンプリング',
            'risk_based': '高リスクアイテムを重点的に選択するリスク重視サンプリング',
            'systematic': '母集団全体から均等に選択する系統的サンプリング',
            'random': '単純無作為抽出による偏りのないサンプリング'
        }
        return justifications.get(method, f'{method}手法によるサンプリング')


