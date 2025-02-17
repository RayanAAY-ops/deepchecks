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
"""Test for the NLP PredictionDrift check"""

from hamcrest import assert_that, close_to, equal_to, has_items

from deepchecks.nlp import TextData
from deepchecks.nlp.checks import PredictionDrift
from tests.base.utils import equal_condition_result


def test_tweet_emotion(tweet_emotion_train_test_textdata, tweet_emotion_train_test_predictions):
    # Arrange
    train, test = tweet_emotion_train_test_textdata
    train_preds, test_preds = tweet_emotion_train_test_predictions
    check = PredictionDrift().add_condition_drift_score_less_than(0.01)
    # Act
    result = check.run(train, test, train_predictions=train_preds,
                       test_predictions=test_preds)
    condition_result = check.conditions_decision(result)

    # Assert
    assert_that(condition_result, has_items(
        equal_condition_result(is_pass=False,
                               details="Found model prediction Cramer's V drift score of 0.04",
                               name='Prediction drift score < 0.01')
    ))

    assert_that(result.value['Drift score'], close_to(0.04, 0.01))


def test_tweet_emotion_no_drift(tweet_emotion_train_test_textdata, tweet_emotion_train_test_predictions):
    # Arrange
    train, _ = tweet_emotion_train_test_textdata
    train_preds, _ = tweet_emotion_train_test_predictions
    check = PredictionDrift().add_condition_drift_score_less_than()
    # Act
    result = check.run(train, train, train_predictions=train_preds, test_predictions=train_preds)
    condition_result = check.conditions_decision(result)

    # Assert
    assert_that(condition_result, has_items(
        equal_condition_result(is_pass=True,
                               details="Found model prediction Cramer's V drift score of 0",
                               name='Prediction drift score < 0.15')
    ))

    assert_that(result.value['Drift score'], equal_to(0))


def test_tweet_emotion_no_drift_no_label(tweet_emotion_train_test_textdata, tweet_emotion_train_test_predictions):
    # Arrange
    train, _ = tweet_emotion_train_test_textdata
    train = TextData(train.text, task_type='text_classification', metadata=train.metadata,
                     properties=train.properties)
    train_preds, _ = tweet_emotion_train_test_predictions
    check = PredictionDrift().add_condition_drift_score_less_than()
    # Act
    result = check.run(train, train, train_predictions=train_preds, test_predictions=train_preds)
    condition_result = check.conditions_decision(result)

    # Assert
    assert_that(condition_result, has_items(
        equal_condition_result(is_pass=True,
                               details="Found model prediction Cramer's V drift score of 0",
                               name='Prediction drift score < 0.15')
    ))

    assert_that(result.value['Drift score'], equal_to(0))
