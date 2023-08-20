# ----------------------------------------------------------------------------
# Copyright (C) 2021-2023 Deepchecks (https://www.deepchecks.com)
#
# This file is part of Deepchecks.
# Deepchecks is distributed under the terms of the GNU Affero General
# Public License (version 3 or later).
# You should have received a copy of the GNU Affero General Public License
# along with Deepchecks.  If not, see <http://www.gnu.org/licenses/>.
# ----------------------------------------------------------------------------
#
"""Module for tabular base checks."""
import abc
import warnings
import typing as t
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from deepchecks.core.check_result import CheckFailure, CheckResult
from deepchecks.core.checks import (BaseCheck, DatasetKind, ModelOnlyBaseCheck, SingleDatasetBaseCheck,
                                    TrainTestBaseCheck)
from deepchecks.core.errors import DeepchecksNotSupportedError, DeepchecksValueError
from deepchecks.tabular import deprecation_warnings  # pylint: disable=unused-import # noqa: F401
from deepchecks.tabular._shared_docs import docstrings
from deepchecks.tabular.context import Context
from deepchecks.tabular.dataset import Dataset
from deepchecks.tabular.model_base import ModelComparisonContext
from deepchecks.tabular.utils.task_type import TaskType
from deepchecks.utils.typing import BasicModel
from deepchecks.recommender.context import Context as RecContext
if TYPE_CHECKING:
    from deepchecks.recommender import InteractionDataset, ItemDataset
__all__ = [
    'SingleDatasetCheck',
    'TrainTestCheck',
    'ModelOnlyCheck',
    'ModelComparisonCheck'
]


class SingleDatasetCheck(SingleDatasetBaseCheck):
    """Parent class for checks that only use one dataset."""

    context_type = None

    @docstrings
    def run(
        self,
        dataset: t.Union[Dataset, pd.DataFrame, 'InteractionDataset'],
        model: t.Optional[BasicModel] = None,
        item_dataset: t.Optional['ItemDataset'] = None,
        interaction_dataset: t.Optional['InteractionDataset'] = None,
        feature_importance: t.Optional[pd.Series] = None,
        feature_importance_force_permutation: bool = False,
        feature_importance_timeout: int = 120,
        with_display: bool = True,
        y_pred: t.Optional[np.ndarray] = None,
        y_proba: t.Optional[np.ndarray] = None,
        y_pred_train: t.Optional[np.ndarray] = None,
        y_pred_test: t.Optional[np.ndarray] = None,
        y_proba_train: t.Optional[np.ndarray] = None,
        y_proba_test: t.Optional[np.ndarray] = None,
        model_classes: t.Optional[t.List] = None,
    ) -> CheckResult:
        """Run check.

        Parameters
        ----------
        dataset: InteractionDataset
            InteractionDataset object representing data about the various interactions between users and items.
        item_dataset: Optional[ItemDataset], default: None
            ItemDataset object representing  various items' data that are being recommended.
        feature_importance: pd.Series , default: None
            pass manual features importance
        feature_importance_force_permutation : bool , default: False
            force calculation of permutation features importance
        feature_importance_timeout : int , default: 120
            timeout in second for the permutation features importance calculation
        y_pred: Optional[np.ndarray] , default: None
            Array of the model prediction over the dataset.
        """
        if dataset.label_type != TaskType.RECOMMENDETION and item_dataset is not None:
            raise DeepchecksNotSupportedError('item_dataset is not supported for tabular datasets.')

        if dataset.label_type == TaskType.RECOMMENDETION and model_classes is not None:
            raise DeepchecksNotSupportedError('model_classes is not supported for recommendation datasets.')

        if y_pred_train is not None:
            warnings.warn('y_pred_train is deprecated, please use y_pred instead.', DeprecationWarning, stacklevel=2)
        if (y_pred_train is not None) and (y_pred is not None):
            raise DeepchecksValueError('Cannot accept both y_pred_train and y_pred, please pass the data only'
                                       ' to y_pred.')
        if y_proba_train is not None:
            warnings.warn('y_proba_train is deprecated, please use y_proba instead.', DeprecationWarning, stacklevel=2)
        if (y_pred_train is not None) and (y_pred is not None):
            raise DeepchecksValueError('Cannot accept both y_proba_train and y_proba, please pass the data only'
                                       ' to y_proba.')

        if y_pred_test is not None:
            warnings.warn('y_pred_test is deprecated and ignored.', DeprecationWarning, stacklevel=2)
        if y_proba_test is not None:
            warnings.warn('y_proba_test is deprecated and ignored.', DeprecationWarning, stacklevel=2)

        y_pred_train = y_pred_train if y_pred_train is not None else y_pred
        y_proba_train = y_proba_train if y_proba_train is not None else y_proba

        if dataset.label_type == TaskType.RECOMMENDETION:
            self.context_type = RecContext
            context = self.context_type(  # pylint: disable=not-callable
                train=dataset,
                item_dataset=item_dataset,
                interaction_dataset=interaction_dataset,
                feature_importance=feature_importance,
                feature_importance_force_permutation=feature_importance_force_permutation,
                feature_importance_timeout=feature_importance_timeout,
                with_display=with_display,
                y_pred_train=y_pred_train,
            )
        else:
            self.context_type = self.context_type or Context
            context = self.context_type(  # pylint: disable=not-callable
                train=dataset,
                model=model,
                feature_importance=feature_importance,
                feature_importance_force_permutation=feature_importance_force_permutation,
                feature_importance_timeout=feature_importance_timeout,
                with_display=with_display,
                y_pred_train=y_pred_train,
                y_proba_train=y_proba_train,
                model_classes=model_classes
            )
        result = self.run_logic(context, dataset_kind=DatasetKind.TRAIN)
        context.finalize_check_result(result, self, DatasetKind.TRAIN)
        return result

    @abc.abstractmethod
    def run_logic(self, context, dataset_kind) -> CheckResult:
        """Run check."""
        raise NotImplementedError()


class TrainTestCheck(TrainTestBaseCheck):
    """Parent class for checks that compare two datasets.

    The class checks train dataset and test dataset for model training and test.
    """

    context_type = None

    @docstrings
    def run(
        self,
        train_dataset: t.Union[Dataset, pd.DataFrame, 'InteractionDataset'],
        test_dataset: t.Union[Dataset, pd.DataFrame, 'InteractionDataset'],
        model: t.Optional[BasicModel] = None,
        item_dataset: t.Optional['ItemDataset'] = None,
        feature_importance: t.Optional[pd.Series] = None,
        feature_importance_force_permutation: bool = False,
        feature_importance_timeout: int = 120,
        with_display: bool = True,
        y_pred_train: t.Optional[np.ndarray] = None,
        y_pred_test: t.Optional[np.ndarray] = None,
        y_proba_train: t.Optional[np.ndarray] = None,
        y_proba_test: t.Optional[np.ndarray] = None,
        model_classes: t.Optional[t.List] = None
    ) -> CheckResult:
        """Run check.

        Parameters
        ----------
        train_dataset: t.Union[Dataset, pd.DataFrame]
            Dataset or DataFrame object, representing data an estimator was fitted on
        test_dataset: t.Union[Dataset, pd.DataFrame]
            Dataset or DataFrame object, representing data an estimator predicts on
        model: t.Optional[BasicModel], default: None
            A scikit-learn-compatible fitted estimator instance
        {additional_context_params:2*indent}
        """
        if train_dataset.label_type != TaskType.RECOMMENDETION and item_dataset is not None:
            raise DeepchecksNotSupportedError('item_dataset is not supported for tabular datasets.')

        if train_dataset.label_type == TaskType.RECOMMENDETION and model_classes is not None:
            raise DeepchecksNotSupportedError('model_classes is not supported for recommendation datasets.')

        if train_dataset.label_type == TaskType.RECOMMENDETION:
            self.context_type = RecContext
            context = self.context_type(  # pylint: disable=not-callable
                train=train_dataset,
                test=test_dataset,
                item_dataset=item_dataset,
                feature_importance=feature_importance,
                feature_importance_force_permutation=feature_importance_force_permutation,
                feature_importance_timeout=feature_importance_timeout,
                y_pred_train=y_pred_train,
                y_pred_test=y_pred_test,
                with_display=with_display,
            )
        else:
            self.context_type = self.context_type or Context
            context = self.context_type(  # pylint: disable=not-callable
                train=train_dataset,
                test=test_dataset,
                model=model,
                feature_importance=feature_importance,
                feature_importance_force_permutation=feature_importance_force_permutation,
                feature_importance_timeout=feature_importance_timeout,
                y_pred_train=y_pred_train,
                y_pred_test=y_pred_test,
                y_proba_train=y_proba_train,
                y_proba_test=y_proba_test,
                with_display=with_display,
                model_classes=model_classes
            )

        result = self.run_logic(context)
        context.finalize_check_result(result, self)
        return result

    @abc.abstractmethod
    def run_logic(self, context) -> CheckResult:
        """Run check."""
        raise NotImplementedError()


class ModelOnlyCheck(ModelOnlyBaseCheck):
    """Parent class for checks that only use a model and no datasets."""

    context_type = Context

    @docstrings
    def run(
        self,
        model: BasicModel,
        feature_importance: t.Optional[pd.Series] = None,
        feature_importance_force_permutation: bool = False,
        feature_importance_timeout: int = 120,
        with_display: bool = True,
        y_pred_train: t.Optional[np.ndarray] = None,
        y_pred_test: t.Optional[np.ndarray] = None,
        y_proba_train: t.Optional[np.ndarray] = None,
        y_proba_test: t.Optional[np.ndarray] = None,
    ) -> CheckResult:
        """Run check.

        Parameters
        ----------
        model: BasicModel
            A scikit-learn-compatible fitted estimator instance
        {additional_context_params:2*indent}
        """
        assert self.context_type is not None
        context = self.context_type(
            model=model,
            feature_importance=feature_importance,
            feature_importance_force_permutation=feature_importance_force_permutation,
            feature_importance_timeout=feature_importance_timeout,
            y_pred_train=y_pred_train,
            y_pred_test=y_pred_test,
            y_proba_train=y_proba_train,
            y_proba_test=y_proba_test,
            with_display=with_display
        )
        result = self.run_logic(context)
        context.finalize_check_result(result, self)
        return result

    @abc.abstractmethod
    def run_logic(self, context) -> CheckResult:
        """Run check."""
        raise NotImplementedError()

    @classmethod
    def _get_unsupported_failure(cls, check, msg):
        return CheckFailure(check, DeepchecksNotSupportedError(msg))


class ModelComparisonCheck(BaseCheck):
    """Parent class for check that compares between two or more models."""

    def run(
        self,
        train_datasets: t.Union[Dataset, t.List[Dataset]],
        test_datasets: t.Union[Dataset, t.List[Dataset]],
        models: t.Union[t.List[BasicModel], t.Mapping[str, BasicModel]]
    ) -> CheckResult:
        """Initialize context and pass to check logic.

        Parameters
        ----------
        train_datasets: t.Union[Dataset, t.List[Dataset]]
            train datasets
        test_datasets: t.Union[Dataset, t.List[Dataset]]
            test datasets
        models: t.Union[t.List[BasicModel], Mapping[str, BasicModel]]
            t.List or map of models
        """
        context = ModelComparisonContext(train_datasets, test_datasets, models)
        result = self.run_logic(context)
        context.finalize_check_result(result, self)
        return result

    @abc.abstractmethod
    def run_logic(self, multi_context: ModelComparisonContext) -> CheckResult:
        """Implement here logic of check."""
        raise NotImplementedError()
