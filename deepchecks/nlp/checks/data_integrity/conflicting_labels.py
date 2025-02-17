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
"""Module contains Conflicting Labels check."""
import typing as t

import pandas as pd

from deepchecks.core import CheckResult
from deepchecks.core.errors import DeepchecksValueError
from deepchecks.nlp import Context, SingleDatasetCheck
from deepchecks.nlp._shared_docs import docstrings
from deepchecks.nlp.task_type import TaskType
from deepchecks.nlp.text_data import TextData
from deepchecks.nlp.utils.text import hash_samples, normalize_samples
from deepchecks.utils.abstracts.conflicting_labels import ConflictingLabelsAbstract
from deepchecks.utils.other import to_ordional_enumeration
from deepchecks.utils.strings import format_list
from deepchecks.utils.strings import get_ellipsis as truncate_string

__all__ = ['ConflictingLabels']


@docstrings
class ConflictingLabels(SingleDatasetCheck, ConflictingLabelsAbstract):
    """Find identical samples which have different labels.

    Parameters
    ----------
    {text_normalization_params:1*indent}
    n_to_show : int , default: 5
        number of most common ambiguous samples to show.
    n_samples : int , default: 10_000_000
        number of samples to use for this check.
    random_state : int, default: 42
        random seed for all check internals.
    {max_text_length_for_display_param:1*indent}
    """

    def __init__(
        self,
        ignore_case: bool = True,
        remove_punctuation: bool = True,
        normalize_unicode: bool = True,
        remove_stopwords: bool = True,
        ignore_whitespace: bool = False,
        n_to_show: int = 5,
        n_samples: int = 10_000_000,
        random_state: int = 42,
        max_text_length_for_display: int = 30,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.ignore_case = ignore_case
        self.remove_punctuation = remove_punctuation
        self.normalize_unicode = normalize_unicode
        self.remove_stopwords = remove_stopwords
        self.ignore_whitespace = ignore_whitespace
        self.n_to_show = n_to_show
        self.n_samples = n_samples
        self.random_state = random_state
        self.max_text_length_for_display = max_text_length_for_display

    @property
    def _text_normalization_kwargs(self):
        return {
            'ignore_case': self.ignore_case,
            'ignore_whitespace': self.ignore_whitespace,
            'normalize_uni': self.normalize_unicode,
            'remove_punct': self.remove_punctuation,
            'remove_stops': self.remove_stopwords,
        }

    def _truncate_text(self, x: str) -> str:
        return truncate_string(x, self.max_text_length_for_display)

    def run_logic(self, context: Context, dataset_kind) -> CheckResult:
        """Run check."""
        dataset = context.get_data_by_kind(dataset_kind).sample(self.n_samples, random_state=self.random_state)
        dataset = t.cast(TextData, dataset)
        samples = dataset.text
        n_of_samples = len(samples)

        if n_of_samples == 0:
            raise DeepchecksValueError('Dataset cannot be empty')

        samples_hashes = hash_samples(normalize_samples(
            dataset.text,
            **self._text_normalization_kwargs
        ))

        if dataset.task_type is TaskType.TOKEN_CLASSIFICATION or dataset.is_multi_label_classification():
            labels = [tuple(t.cast(t.Sequence[t.Any], it)) for it in dataset.label]
        elif dataset.task_type is TaskType.TEXT_CLASSIFICATION:
            labels = dataset.label
        else:
            raise DeepchecksValueError(f'Unknow task type - {dataset.task_type}')

        df = pd.DataFrame({
            'hash': samples_hashes,
            'Sample ID': dataset.get_original_text_indexes(),
            'Label': labels,
            'Text': dataset.text,
        })

        by_hash = df.loc[:, ['hash', 'Label']].groupby(['hash'], dropna=False)
        count_labels = lambda x: len(set(x.to_list()))
        n_of_labels_per_sample = by_hash['Label'].aggregate(count_labels)

        ambiguous_samples_hashes = n_of_labels_per_sample[n_of_labels_per_sample > 1]
        ambiguous_samples_hashes = frozenset(ambiguous_samples_hashes.index.to_list())

        ambiguous_samples = df[df['hash'].isin(ambiguous_samples_hashes)]
        num_of_ambiguous_samples = ambiguous_samples['Text'].count()
        percent_of_ambiguous_samples = num_of_ambiguous_samples / n_of_samples

        result_df = ambiguous_samples.rename(columns={'hash': 'Duplicate'})
        duplicates_enumeration = to_ordional_enumeration(result_df['Duplicate'].to_list())
        result_df['Duplicate'] = result_df['Duplicate'].apply(lambda x: duplicates_enumeration[x])
        result_df = result_df.set_index(['Duplicate', 'Sample ID', 'Label'])

        result_value = {
            'percent_of_conflicting_samples': percent_of_ambiguous_samples,
            'conflicting_samples': result_df,
        }

        if context.with_display is False:
            return CheckResult(value=result_value)

        ambiguous_samples['Text'] = ambiguous_samples['Text'].apply(self._truncate_text)
        by_hash = ambiguous_samples.groupby(['hash'], dropna=False)
        observed_labels = by_hash['Label'].aggregate(lambda x: format_list(x.to_list()))
        samples_ids = by_hash['Sample ID'].aggregate(lambda x: format_list(x.to_list(), max_string_length=200))
        first_in_group = by_hash['Text'].first()

        display_table = (
            pd.DataFrame({
                # TODO:
                # for multi-label and token classification
                # 'Observed Labels' column will look not very nice
                # need an another way to display observed labels
                # for those task types
                'Observed Labels': observed_labels,
                'Sample IDs': samples_ids,
                'Text': first_in_group
            })
            .reset_index(drop=True)
            .set_index(['Observed Labels', 'Sample IDs'])
        )
        table_description = (
            'Each row in the table shows an example of a data sample '
            'and the its observed conflicting labels as found in the dataset.'
        )
        table_note = (
            f'Showing top {self.n_to_show} of {len(display_table)}'
            if self.n_to_show <= len(display_table)
            else ''
        )
        return CheckResult(
            value=result_value,
            display=[
                table_description,
                table_note,
                # slice over first level of the multiindex ('Observed Labels')
                display_table.iloc[slice(0, self.n_to_show)]
            ]
        )
