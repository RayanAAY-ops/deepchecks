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
"""Module containing the popularity bias check."""
import typing as t

import pandas as pd

from deepchecks.core import CheckResult
from deepchecks.core.condition import ConditionCategory, ConditionResult
from deepchecks.core.errors import DeepchecksValueError
from deepchecks.recommender import Context
from deepchecks.tabular import TrainTestCheck
from deepchecks.utils.distribution.drift import calc_drift_and_plot
from deepchecks.utils.validation import is_sequence_not_str

__all__ = ['UserSessionDrift']

class UserSessionDrift(TrainTestCheck):
    """
    
    Check for user session length bias in train and validation sets. This check compares the distribution of user session lengths between the train and validation sets to identify potential bias or discrepancies. It helps assess whether the two sets exhibit similar patterns in terms of user session lengths or if there are significant differences that could introduce bias in the recommender system.
    
    """
    def __init__(
            self,
            margin_quantile_filter: float = 0.025,
            max_num_categories_for_drift: int = None,
            min_category_size_ratio: float = 0.01,
            max_num_categories_for_display: int = 10,
            show_categories_by: str = 'largest_difference',
            numerical_drift_method: str = 'KS',
            categorical_drift_method: str = 'cramers_v',
            balance_classes: bool = False,
            ignore_na: bool = True,
            aggregation_method: t.Optional[str] = 'max',
            min_samples: t.Optional[int] = 10,
            n_samples: int = 100_000,
            random_state: int = 42,
            **kwargs
    ):
        super().__init__(**kwargs)
        self.margin_quantile_filter = margin_quantile_filter
        self.max_num_categories_for_drift = max_num_categories_for_drift
        self.min_category_size_ratio = min_category_size_ratio
        self.max_num_categories_for_display = max_num_categories_for_display
        self.show_categories_by = show_categories_by
        self.numerical_drift_method = numerical_drift_method
        self.categorical_drift_method = categorical_drift_method
        self.balance_classes = balance_classes
        self.ignore_na = ignore_na
        self.aggregation_method = aggregation_method
        self.min_samples = min_samples
        self.n_samples = n_samples
        self.random_state = random_state
        if self.aggregation_method not in ('weighted', 'mean', 'none', None, 'max'):
            raise DeepchecksValueError('aggregation_method must be one of "weighted", "mean", "max", None')

    def run_logic(self, context: Context) -> CheckResult:
        """Calculate drift for all columns.

        Returns
        -------
        CheckResult
            value: drift score.
            display: label distribution graph, comparing the train and test distributions.
        """

        train_dataset = context.train
        test_dataset = context.test

        user_col = train_dataset.user_index_name
        assert user_col == test_dataset.user_index_name

        train_user_session_length = train_dataset.data[user_col].value_counts().tolist()
        test_user_session_length = test_dataset.data[user_col].value_counts().tolist()


        drift_score, method, drift_display = calc_drift_and_plot(
            train_column=pd.Series(train_user_session_length),
            test_column=pd.Series(test_user_session_length),
            value_name='Session Length',
            column_type='numerical',
            plot_title='Session Length Drift',
            margin_quantile_filter=self.margin_quantile_filter,
            max_num_categories_for_drift=self.max_num_categories_for_drift,
            min_category_size_ratio=self.min_category_size_ratio,
            max_num_categories_for_display=self.max_num_categories_for_display,
            show_categories_by=self.show_categories_by,
            numerical_drift_method=self.numerical_drift_method,
            categorical_drift_method=self.categorical_drift_method,
            balance_classes=self.balance_classes,
            ignore_na=self.ignore_na,
            min_samples=self.min_samples,
            raise_min_samples_error=True,
            dataset_names=('Train', 'Test'),
            with_display=context.with_display,
        )

        return CheckResult(
            value=drift_score,
            header='Session Length Bias',
            display=drift_display,
        )

    def add_condition_drift_score_less_than(self, max_allowed_score: float = 0.15):
        """
        Add condition - require drift score to be less than a certain threshold.

        The industry standard for PSI limit is above 0.2.
        There are no common industry standards for other drift methods, such as Cramer's V,
        Kolmogorov-Smirnov and Earth Mover's Distance.
        The threshold was lowered by 25% compared to feature drift defaults due to the higher importance of prediction
        drift.

        Parameters
        ----------
        max_allowed_categorical_score: float , default: 0.15
            the max threshold for the categorical variable drift score
        max_allowed_numeric_score: float ,  default: 0.15
            the max threshold for the numeric variable drift score
        Returns
        -------
        ConditionResult
            False if any column has passed the max threshold, True otherwise
        """

        def condition(result: float) -> ConditionResult:
            category = ConditionCategory.FAIL if result > max_allowed_score else ConditionCategory.PASS
            return ConditionResult(category, f'The drift score was {result}')

        return self.add_condition(f'drift score less than {max_allowed_score}', condition)
