"""Testing for the boost module (sklearn.ensemble.boost)."""

import pytest
import numpy as np

from sklearn.utils.testing import assert_array_equal, assert_array_less
from sklearn.utils.testing import assert_array_almost_equal
from sklearn.utils.testing import assert_equal, assert_greater
from sklearn.utils.testing import assert_raises, assert_raises_regexp

from sklearn.base import BaseEstimator
from sklearn.model_selection import GridSearchCV
from sklearn.ensemble import AdaBoostClassifier
from sklearn.ensemble import AdaBoostRegressor
from sklearn.ensemble import weight_boosting
from sklearn.svm import SVC, SVR
from sklearn.tree import DecisionTreeClassifier, DecisionTreeRegressor
from sklearn.utils import shuffle
from sklearn import datasets


# Common random state
rng = np.random.RandomState(0)

# Toy sample
X = [[-2, -1], [-1, -1], [-1, -2], [1, 1], [1, 2], [2, 1]]
y_class = ["foo", "foo", "foo", 1, 1, 1]    # test string class labels
y_regr = [-1, -1, -1, 1, 1, 1]
T = [[-1, -1], [2, 2], [3, 2]]
y_t_class = ["foo", 1, 1]
y_t_regr = [-1, 1, 1]

# Load the iris dataset and randomly permute it
iris = datasets.load_iris()
perm = rng.permutation(iris.target.size)
iris.data, iris.target = shuffle(iris.data, iris.target, random_state=rng)

# Load the boston dataset and randomly permute it
boston = datasets.load_boston()
boston.data, boston.target = shuffle(boston.data, boston.target,
                                     random_state=rng)


def test_samme_proba():
    # Test the `_samme_proba` helper function.

    # Define some example (bad) `predict_proba` output.
    probs = np.array([[1, 1e-6, 0],
                      [0.19, 0.6, 0.2],
                      [-999, 0.51, 0.5],
                      [1e-6, 1, 1e-9]])
    probs /= np.abs(probs.sum(axis=1))[:, np.newaxis]

    # _samme_proba calls estimator.predict_proba.
    # Make a mock object so I can control what gets returned.
    class MockEstimator:
        def predict_proba(self, X):
            assert_array_equal(X.shape, probs.shape)
            return probs
    mock = MockEstimator()

    samme_proba = weight_boosting._samme_proba(mock, 3, np.ones_like(probs))

    assert_array_equal(samme_proba.shape, probs.shape)
    assert np.isfinite(samme_proba).all()

    # Make sure that the correct elements come out as smallest --
    # `_samme_proba` should preserve the ordering in each example.
    assert_array_equal(np.argmin(samme_proba, axis=1), [2, 0, 0, 2])
    assert_array_equal(np.argmax(samme_proba, axis=1), [0, 1, 1, 1])


def test_oneclass_adaboost_proba():
    # Test predict_proba robustness for one class label input.
    # In response to issue #7501
    # https://github.com/scikit-learn/scikit-learn/issues/7501
    y_t = np.ones(len(X))
    clf = AdaBoostClassifier().fit(X, y_t)
    assert_array_almost_equal(clf.predict_proba(X), np.ones((len(X), 1)))


def test_classification_toy():
    # Check classification on a toy dataset.
    for alg in ['SAMME', 'SAMME.R']:
        clf = AdaBoostClassifier(algorithm=alg, random_state=0)
        clf.fit(X, y_class)
        assert_array_equal(clf.predict(T), y_t_class)
        assert_array_equal(np.unique(np.asarray(y_t_class)), clf.classes_)
        assert_equal(clf.predict_proba(T).shape, (len(T), 2))
        assert_equal(clf.decision_function(T).shape, (len(T),))


def test_regression_toy():
    # Check classification on a toy dataset.
    clf = AdaBoostRegressor(random_state=0)
    clf.fit(X, y_regr)
    assert_array_equal(clf.predict(T), y_t_regr)


def test_iris():
    # Check consistency on dataset iris.
    classes = np.unique(iris.target)
    clf_samme = prob_samme = None

    for alg in ['SAMME', 'SAMME.R']:
        clf = AdaBoostClassifier(algorithm=alg)
        clf.fit(iris.data, iris.target)

        assert_array_equal(classes, clf.classes_)
        proba = clf.predict_proba(iris.data)
        if alg == "SAMME":
            clf_samme = clf
            prob_samme = proba
        assert_equal(proba.shape[1], len(classes))
        assert_equal(clf.decision_function(iris.data).shape[1], len(classes))

        score = clf.score(iris.data, iris.target)
        assert score > 0.9, "Failed with algorithm %s and score = %f" % \
            (alg, score)

        # Check we used multiple estimators
        assert_greater(len(clf.estimators_), 1)
        # Check for distinct random states (see issue #7408)
        assert_equal(len(set(est.random_state for est in clf.estimators_)),
                     len(clf.estimators_))

    # Somewhat hacky regression test: prior to
    # ae7adc880d624615a34bafdb1d75ef67051b8200,
    # predict_proba returned SAMME.R values for SAMME.
    clf_samme.algorithm = "SAMME.R"
    assert_array_less(0,
                      np.abs(clf_samme.predict_proba(iris.data) - prob_samme))


def test_boston():
    # Check consistency on dataset boston house prices.
    reg = AdaBoostRegressor(random_state=0)
    reg.fit(boston.data, boston.target)
    score = reg.score(boston.data, boston.target)
    assert score > 0.85

    # Check we used multiple estimators
    assert len(reg.estimators_) > 1
    # Check for distinct random states (see issue #7408)
    assert_equal(len(set(est.random_state for est in reg.estimators_)),
                 len(reg.estimators_))


def test_staged_predict():
    # Check staged predictions.
    rng = np.random.RandomState(0)
    iris_weights = rng.randint(10, size=iris.target.shape)
    boston_weights = rng.randint(10, size=boston.target.shape)

    # AdaBoost classification
    for alg in ['SAMME', 'SAMME.R']:
        clf = AdaBoostClassifier(algorithm=alg, n_estimators=10)
        clf.fit(iris.data, iris.target, sample_weight=iris_weights)

        predictions = clf.predict(iris.data)
        staged_predictions = [p for p in clf.staged_predict(iris.data)]
        proba = clf.predict_proba(iris.data)
        staged_probas = [p for p in clf.staged_predict_proba(iris.data)]
        score = clf.score(iris.data, iris.target, sample_weight=iris_weights)
        staged_scores = [
            s for s in clf.staged_score(
                iris.data, iris.target, sample_weight=iris_weights)]

        assert_equal(len(staged_predictions), 10)
        assert_array_almost_equal(predictions, staged_predictions[-1])
        assert_equal(len(staged_probas), 10)
        assert_array_almost_equal(proba, staged_probas[-1])
        assert_equal(len(staged_scores), 10)
        assert_array_almost_equal(score, staged_scores[-1])

    # AdaBoost regression
    clf = AdaBoostRegressor(n_estimators=10, random_state=0)
    clf.fit(boston.data, boston.target, sample_weight=boston_weights)

    predictions = clf.predict(boston.data)
    staged_predictions = [p for p in clf.staged_predict(boston.data)]
    score = clf.score(boston.data, boston.target, sample_weight=boston_weights)
    staged_scores = [
        s for s in clf.staged_score(
            boston.data, boston.target, sample_weight=boston_weights)]

    assert_equal(len(staged_predictions), 10)
    assert_array_almost_equal(predictions, staged_predictions[-1])
    assert_equal(len(staged_scores), 10)
    assert_array_almost_equal(score, staged_scores[-1])


@pytest.mark.filterwarnings('ignore: The default of the `iid`')  # 0.22
@pytest.mark.filterwarnings('ignore: You should specify a value')  # 0.22
def test_gridsearch():
    # Check that base trees can be grid-searched.
    # AdaBoost classification
    boost = AdaBoostClassifier(base_estimator=DecisionTreeClassifier())
    parameters = {'n_estimators': (1, 2),
                  'base_estimator__max_depth': (1, 2),
                  'algorithm': ('SAMME', 'SAMME.R')}
    clf = GridSearchCV(boost, parameters)
    clf.fit(iris.data, iris.target)

    # AdaBoost regression
    boost = AdaBoostRegressor(base_estimator=DecisionTreeRegressor(),
                              random_state=0)
    parameters = {'n_estimators': (1, 2),
                  'base_estimator__max_depth': (1, 2)}
    clf = GridSearchCV(boost, parameters)
    clf.fit(boston.data, boston.target)


def test_pickle():
    # Check pickability.
    import pickle

    # Adaboost classifier
    for alg in ['SAMME', 'SAMME.R']:
        obj = AdaBoostClassifier(algorithm=alg)
        obj.fit(iris.data, iris.target)
        score = obj.score(iris.data, iris.target)
        s = pickle.dumps(obj)

        obj2 = pickle.loads(s)
        assert_equal(type(obj2), obj.__class__)
        score2 = obj2.score(iris.data, iris.target)
        assert_equal(score, score2)

    # Adaboost regressor
    obj = AdaBoostRegressor(random_state=0)
    obj.fit(boston.data, boston.target)
    score = obj.score(boston.data, boston.target)
    s = pickle.dumps(obj)

    obj2 = pickle.loads(s)
    assert_equal(type(obj2), obj.__class__)
    score2 = obj2.score(boston.data, boston.target)
    assert_equal(score, score2)


def test_importances():
    # Check variable importances.
    X, y = datasets.make_classification(n_samples=2000,
                                        n_features=10,
                                        n_informative=3,
                                        n_redundant=0,
                                        n_repeated=0,
                                        shuffle=False,
                                        random_state=1)

    for alg in ['SAMME', 'SAMME.R']:
        clf = AdaBoostClassifier(algorithm=alg)

        clf.fit(X, y)
        importances = clf.feature_importances_

        assert_equal(importances.shape[0], 10)
        assert_equal((importances[:3, np.newaxis] >= importances[3:]).all(),
                     True)


def test_error():
    # Test that it gives proper exception on deficient input.
    assert_raises(ValueError,
                  AdaBoostClassifier(learning_rate=-1).fit,
                  X, y_class)

    assert_raises(ValueError,
                  AdaBoostClassifier(algorithm="foo").fit,
                  X, y_class)

    assert_raises(ValueError,
                  AdaBoostClassifier().fit,
                  X, y_class, sample_weight=np.asarray([-1]))


@pytest.mark.filterwarnings('ignore:The default value of n_estimators')
def test_base_estimator():
    # Test different base estimators.
    from sklearn.ensemble import RandomForestClassifier

    # XXX doesn't work with y_class because RF doesn't support classes_
    # Shouldn't AdaBoost run a LabelBinarizer?
    clf = AdaBoostClassifier(RandomForestClassifier())
    clf.fit(X, y_regr)

    clf = AdaBoostClassifier(SVC(gamma="scale"), algorithm="SAMME")
    clf.fit(X, y_class)

    from sklearn.ensemble import RandomForestRegressor

    clf = AdaBoostRegressor(RandomForestRegressor(), random_state=0)
    clf.fit(X, y_regr)

    clf = AdaBoostRegressor(SVR(gamma='scale'), random_state=0)
    clf.fit(X, y_regr)

    # Check that an empty discrete ensemble fails in fit, not predict.
    X_fail = [[1, 1], [1, 1], [1, 1], [1, 1]]
    y_fail = ["foo", "bar", 1, 2]
    clf = AdaBoostClassifier(SVC(gamma="scale"), algorithm="SAMME")
    assert_raises_regexp(ValueError, "worse than random",
                         clf.fit, X_fail, y_fail)


def test_sample_weight_missing():
    from sklearn.cluster import KMeans

    clf = AdaBoostClassifier(KMeans(), algorithm="SAMME")
    assert_raises(ValueError, clf.fit, X, y_regr)

    clf = AdaBoostRegressor(KMeans())
    assert_raises(ValueError, clf.fit, X, y_regr)


def test_sample_weight_adaboost_regressor():
    """
    AdaBoostRegressor should work without sample_weights in the base estimator

    The random weighted sampling is done internally in the _boost method in
    AdaBoostRegressor.
    """
    class DummyEstimator(BaseEstimator):

        def fit(self, X, y):
            pass

        def predict(self, X):
            return np.zeros(len(X))

    boost = AdaBoostRegressor(DummyEstimator(), n_estimators=3)
    boost.fit(X, y_regr)
    assert_equal(len(boost.estimator_weights_), len(boost.estimator_errors_))


def test_multidimensional_X():
    class DummyClassifier(BaseEstimator):

        def fit(self, X, y, sample_weight=None):
            self.classes_ = np.unique(y)
            return self

        def predict(self, X):
            n_samples = len(X)
            predictions = np.random.choice(self.classes_, n_samples)
            return predictions

        def predict_proba(self, X):
            n_samples = len(X)
            n_classes = len(self.classes_)
            probas = np.random.randn(n_samples, n_classes)
            return probas

    class DummyRegressor(BaseEstimator):

        def fit(self, X, y):
            return self

        def predict(self, X):
            n_samples = len(X)
            predictions = np.random.randn(n_samples)
            return predictions

    X = np.random.randn(50, 3, 3).tolist()
    yc = np.random.choice([0, 1], 50)
    yr = np.random.randn(50)

    boost = AdaBoostClassifier(DummyClassifier())
    boost.fit(X, yc)

    boost = AdaBoostRegressor(DummyRegressor())
    boost.fit(X, yr)

