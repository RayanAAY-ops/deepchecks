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
"""Module for base recsys context."""
import typing as t

import numpy as np
import pandas as pd

from deepchecks.core.errors import DeepchecksValueError
from deepchecks.recommender.dataset import ItemDataset, UserDataset, InteractionDataset
from deepchecks.tabular._shared_docs import docstrings
from deepchecks.tabular.context import Context as TabularContext
from deepchecks.tabular.dataset import Dataset
from deepchecks.tabular.metric_utils.scorers import DeepcheckScorer
from deepchecks.utils.function import run_available_kwargs
from deepchecks.utils.logger import get_logger
from deepchecks.utils.validation import is_sequence_not_str

from . import ranking

__all__ = [
    'Context'
]


class _DummyModel:
    """Dummy model class used for inference with static predictions from the user.

    Parameters
    ----------
    train: Dataset
        Dataset, representing data an estimator was fitted on.
    test: Dataset
        Dataset, representing data an estimator predicts on.
    y_pred_train: t.Optional[np.ndarray]
        Array of the model prediction over the train dataset.
    y_pred_test: t.Optional[np.ndarray]
        Array of the model prediction over the test dataset.
    validate_data_on_predict: bool, default = True
        If true, before predicting validates that the received data samples have the same index as in original data.
    """

    feature_df_list: t.List[pd.DataFrame]
    predictions: pd.DataFrame

    def __init__(self,
                 train: t.Union[Dataset, None] = None,
                 test: t.Union[Dataset, None] = None,
                 y_pred_train: t.Optional[t.Sequence[t.Hashable]] = None,
                 y_pred_test: t.Optional[t.Sequence[t.Hashable]] = None,
                 validate_data_on_predict: bool = True):

        if train is not None and test is not None:
            # check if datasets have same indexes
            if set(train.data.index) & set(test.data.index):
                train.data.index = map(lambda x: f'train-{x}', list(train.data.index))
                test.data.index = map(lambda x: f'test-{x}', list(test.data.index))
                get_logger().warning('train and test datasets have common index - adding "train"/"test"'
                                     ' prefixes. To avoid that provide datasets with no common indexes '
                                     'or pass the model object instead of the predictions.')

        feature_df_list = []
        predictions = []

        for dataset, y_pred in zip([train, test],
                                   [y_pred_train, y_pred_test]):
            if dataset is not None:
                feature_df_list.append(dataset.features_columns)
                if y_pred is not None:
                    y_pred_ser = pd.Series(y_pred, index=dataset.data.index)
                    predictions.append(y_pred_ser)

        self.predictions = pd.concat(predictions, axis=0) if predictions else None
        self.feature_df_list = feature_df_list
        self.validate_data_on_predict = validate_data_on_predict

        if self.predictions is not None:
            self.predict = self._predict

    def _validate_data(self, data: pd.DataFrame):
        data = data.sample(min(100, len(data)))
        for feature_df in self.feature_df_list:
            # If all indices are found than test for equality in actual data (statistically significant portion)
            if set(data.index).issubset(set(feature_df.index)):
                sample_data = np.unique(np.random.choice(data.index, 30))
                if feature_df.loc[sample_data].equals(data.loc[sample_data]):
                    return
                else:
                    break
        raise DeepchecksValueError('Data that has not been seen before passed for inference with static '
                                   'predictions. Pass a real model to resolve this')

    def _predict(self, data: pd.DataFrame):
        """Predict on given data by the data indexes."""
        if self.validate_data_on_predict:
            self._validate_data(data)
        return self.predictions.loc[data.index].to_numpy()


class Scorer(DeepcheckScorer):
    """
    A custom scoring class for evaluating recommendation system models.

    Args:
        metric (callable or str or dict): The metric to use for scoring. Can be a callable function,
            a string representing a metric function name from the 'ranking' module, or a dictionary
            containing the metric name.
        name (str): The name of the scorer.
        to_avg (bool, optional): Whether to average the scores across samples. Defaults to True.
        **kwargs: Additional keyword arguments to be passed to the metric function.

    Attributes:
        per_sample_metric (callable): The metric function to be used for per-sample scoring.
        to_avg (bool): Indicates whether scores should be averaged.
        metric_kwargs (dict): Additional keyword arguments for the metric function.

    Methods:
        run_rec_metric(y_true, y_pred): Runs the recommendation metric on the provided true labels
            and predicted recommendations.
        __call__(model, dataset): Computes the score of the model on the given dataset.
        _run_score(model, data, label_col): Computes the score of the model on the provided data
            using the label column.

    Note:
        This class assumes that the 'DeepcheckScorer' class is its parent class.

    Example:
        scorer = Scorer(metric='precision_at_k', name='Precision@K', to_avg=True, k=5)
        model = YourRecommendationModel()
        dataset = YourDataset()
        score = scorer(model, dataset)
    """

    def __init__(self, metric, name, to_avg=True, k=None, **kwargs):
        if isinstance(metric, t.Callable):
            self.per_sample_metric = metric
        elif isinstance(metric, str):
            self.per_sample_metric = getattr(ranking, metric)
        elif isinstance(metric, dict):
            self.per_sample_metric = getattr(ranking, list(metric.values())[0])
        else:
            raise DeepchecksValueError('Wrong scorer type')

        super().__init__(self.per_sample_metric, name=name, model_classes=None, observed_classes=None)
        self.to_avg = to_avg
        self.metric_kwargs = kwargs
        self.k = k

    def run_rec_metric(self, y_true, y_pred):
        """
        Calculate the recommendation metric on the provided true labels and predicted recommendations.

        Args:
            y_true: True labels representing the relevance of items.
            y_pred: Predicted recommendations by the model.

        Returns:
            Metric scores calculated based on the provided inputs.
        """
        return run_available_kwargs(self.per_sample_metric,
                                    relevant_items=y_true,
                                    recommendations=y_pred,
                                    k=self.k,
                                    **self.metric_kwargs)

    def __call__(self, model, dataset: t.Union[UserDataset, ItemDataset, InteractionDataset]):
        dataset_without_nulls = self.filter_nulls(dataset)
        y_true = dataset_without_nulls.label_col
        y_pred = model.predict(dataset_without_nulls.features_columns)
        scores = self.run_rec_metric(y_true, y_pred)
        if self.to_avg:
            return pd.Series(scores).mean()
        return scores

    def _run_score(self, model, data: pd.DataFrame, label_col: pd.Series):
        """
        Compute the score of the model on the provided data using the label column.

        Args:
            model: The recommendation model to be evaluated.
            data: Data to be used for prediction.
            label_col: True labels representing the relevance of items.

        Returns:
            The computed score based on the provided model, data, and label column.
        """
        y_pred = model.predict(data)
        scores = self.run_rec_metric(label_col, y_pred)
        if self.to_avg:
            return pd.Series(scores).mean()
        return scores


@docstrings
class Context(TabularContext):
    """Contains all the data + properties the user has passed to a check/suite, and validates it seamlessly.

    Parameters
    ----------
    train: RecDataset , default: None
        RecDataset object (dataset object for recommendation systems), representing data an estimator was fitted on
    test: RecDataset , default: None
        RecDataset object (dataset object for recommendation systems), representing data an estimator was fitted on
    feature_importance: pd.Series , default: None
        pass manual features importance
    feature_importance_force_permutation : bool , default: False
        force calculation of permutation features importance
    feature_importance_timeout : int , default: 120
        timeout in second for the permutation features importance calculation
    y_pred_train: Optional[np.ndarray] , default: None
        Array of the model prediction over the train dataset.
    y_pred_test: Optional[np.ndarray] , default: None
        Array of the model prediction over the test dataset.
    """

    def __init__(
        self,
        train: t.Union[UserDataset, ItemDataset, InteractionDataset] = None,
        test: t.Union[UserDataset, ItemDataset, InteractionDataset] = None,
        item_dataset: t.Optional[ItemDataset] = None,
        interaction_dataset: t.Optional[InteractionDataset] = None,
        feature_importance: t.Optional[pd.Series] = None,
        feature_importance_force_permutation: bool = False,
        feature_importance_timeout: int = 120,
        with_display: bool = True,
        y_pred_train: t.Optional[t.Sequence[t.Hashable]] = None,
        y_pred_test: t.Optional[t.Sequence[t.Hashable]] = None,
    ):
        model = _DummyModel(train=train, test=test, y_pred_train=y_pred_train, y_pred_test=y_pred_test)
        self._item_dataset = item_dataset
        self._interaction_dataset = interaction_dataset
        self._item_popularity = None
        self._y_pred_train = y_pred_train
        self._y_pred_test = y_pred_test
        super().__init__(train=train,
                         test=test,
                         feature_importance=feature_importance,
                         feature_importance_force_permutation=feature_importance_force_permutation,
                         feature_importance_timeout=feature_importance_timeout,
                         with_display=with_display)
        self._model = model

    def get_scorer_kwargs(self) -> t.Dict:
        """
        Get keyword arguments for configuring scorers.

        Returns:
            dict: A dictionary containing keyword arguments for configuring scorers.
        """
        if self._item_dataset is not None:
            item_to_index = self._item_dataset.item_index_to_ordinal
        else:
            item_to_index = None

        if self.train.user_index_name is not None:
            num_users = self.train.data[self.train.user_index_name].nunique()
        else:
            num_users = None

        return {'item_to_index': item_to_index,
                'item_popularity': self.item_popularity, 'num_users': num_users,
                'item_features':  pd.DataFrame(self._item_dataset.features_columns.values,
                                               index=self._item_dataset.data[self._item_dataset.item_index_name])
                if self._item_dataset is not None else None}

    def get_scorers(self, scorers: t.Union[t.Mapping[str, t.Union[str, t.Callable]],
                                           t.List[str]] = None, use_avg_defaults=True, k=10) -> t.List[Scorer]:
        """
        Get a list of Scorer instances based on specified or default scorers.

        Args:
            scorers (Union[Mapping[str, Union[str, Callable]], List[str]], optional):
                A mapping of scorer names to scorer functions or a list of scorer names. Defaults to None.
            use_avg_defaults (bool, optional):
                Whether to use average defaults for scorers. Defaults to True.

        Returns:
            list: A list of Scorer instances.
        """
        if scorers is None:
            return [Scorer('reciprocal_rank', to_avg=use_avg_defaults, name=None, **self.get_scorer_kwargs())]
        if isinstance(scorers, t.Mapping):
            scorers = [Scorer(scorer, name, to_avg=use_avg_defaults, k=k, **self.get_scorer_kwargs())
                       for name, scorer in scorers.items()]
        else:
            scorers = [Scorer(scorer, to_avg=use_avg_defaults, name=None, k=k, **self.get_scorer_kwargs())
                       for scorer in scorers]
        return scorers

    def get_single_scorer(self, scorer: t.Mapping[str, t.Union[str, t.Callable]] = None,
                          use_avg_defaults=True, k=10) -> DeepcheckScorer:
        """
        Get a single Scorer instance based on a specified or default scorer.

        Args:
            scorer (Mapping[str, Union[str, Callable]], optional):
                A mapping of scorer names to scorer functions. Defaults to None.
            use_avg_defaults (bool, optional):
                Whether to use average defaults for scorers. Defaults to True.

        Returns:
            DeepcheckScorer: A Scorer instance.
        """
        if scorer is None:
            return Scorer('reciprocal_rank', to_avg=use_avg_defaults, name=None, **self.get_scorer_kwargs())
        return Scorer(scorer, to_avg=use_avg_defaults, name=None, k=k, **self.get_scorer_kwargs())

    @property
    def model_classes(self) -> t.List:
        """
        Return ordered list of possible label classes for classification tasks or None for regression.

        Returns:
            list: An ordered list of possible label classes or None.
        """
        if self._model_classes is None:
            return self.observed_classes
        return self._model_classes

    @property
    def observed_classes(self) -> t.List:
        """
        Return the observed classes in both train and test sets.

        Returns:
            list: A list of observed classes.
        """
        if self._observed_classes is None:
            if is_sequence_not_str(self.train.label_col.iloc[0]):
                labels = [item for sublist in self.train.label_col for item in sublist]
            else:
                labels = self.train.label_col
            self._observed_classes = sorted(pd.Series(labels).dropna().unique().tolist())
        return self._observed_classes

    @property
    def item_popularity(self) -> t.List:
        """
        Return item popularity based on appearance in the train set.

        Returns:
            list: A list of item popularity values.
        """
        if self._item_popularity is None:
            if is_sequence_not_str(self.train.label_col.iloc[0]):
                self._item_popularity = pd.Series([item for sublist in self.train.label_col for item in sublist])\
                    .value_counts(ascending=False).to_dict()
            else:
                self._item_popularity = self.train.label_col.value_counts(ascending=False).to_dict()
        return self._item_popularity

    @property
    def get_item_dataset(self):
        """Return interaction dataset."""
        if self._item_dataset is None:
            return self._item_dataset
        return self._item_dataset

    @property
    def get_interaction_dataset(self):
        """Return interaction dataset."""
        if self._interaction_dataset is None:
            return self._interaction_dataset
        return self._interaction_dataset
