import json
import os

import unitok.configs.english
from unitok import unitok as tok

import gensim
import numpy
from scipy.spatial.distance import cosine
from sklearn.metrics import mean_absolute_error
from sklearn.model_selection import KFold
import yaml



###
#   Configuration helpers
###

def __read_config():
    '''Reads the config.yml file and returns the Yaml config file as a
    dictionary.

    Void -> dict
    '''

    with open('config.yml', 'r') as fp:
        return yaml.load(fp.read())

def __root_path():
    '''Returns the project directories path.

    Void -> String
    '''

    return os.path.abspath(os.path.join(__file__, os.pardir))

def config_path(key_list):
    '''Using __read_config and __root_path it returns the absolute file path
    to the path name stored at the key value of the last key in the key list.
    E.g. if a value is stored in the YAMl file under mongo and then user name
    then the key list will be ['mongo', 'user name'] the value stored their
    will be a path in relation to the project directory.

    list of strings -> String
    '''

    key_list_copy = list(key_list)
    config_dict = __read_config()
    while key_list_copy:
        config_dict = config_dict[key_list_copy.pop(0)]
    full_config_path = os.path.join(__root_path(), config_dict)
    return full_config_path


###
#   LSTM pre-processing helpers
###

def max_length(texts):
    '''Given a list of strings it will return the length of the string with the
    most tokens. Where length is measured in number of tokens. unitok_tokens
    method is used to identify tokens.

    List of strings -> Integer
    '''

    max_token_length = 0
    for text in texts:
        tokens = unitok_tokens(text)
        if len(tokens) > max_token_length:
            max_token_length = len(tokens)
    return max_token_length

def process_data(texts, wordvec_model, max_token_length):
    '''Given a list of Strings a word2vec model and the maximum token length
    it will return a 3 dimensional numpy array of the following shape:
    (number of texts, word2vec model vector size, max token length).

    Each text will have each token mapped to a vector in the word2vec model. If
    the token does not exist then a vector of zeros will be inserted instead.
    The vector of zero applices when the text has no more tokens but has not
    reached the mex token length (This is also called padding).

    List of strings, gensim.models.Word2Vec, Integer -> 3D Numpy array.
    '''

    vector_length = wordvec_model.vector_size
    all_vectors = []

    for text in texts:
        vector_format = []
        tokens = unitok_tokens(text)[0:max_token_length]
        for token in tokens:
            if token in wordvec_model.vocab:
                vector_format.append(wordvec_model[token].reshape(1,vector_length))
            else:
                vector_format.append(numpy.zeros(300).reshape(1,vector_length))
        while len(vector_format) != max_token_length:
            vector_format.append(numpy.zeros(vector_length).reshape(1,vector_length))
        all_vectors.append(numpy.vstack(vector_format))
    return numpy.asarray(all_vectors)


###
#   Tokeniser
###

def unitok_tokens(text):
    '''Tokenises using unitok http://corpus.tools/wiki/Unitok the text. Given
    a string of text returns a list of strings (tokens) that are sub strings
    of the original text. It does not return any whitespace.

    String -> List of Strings
    '''

    tokens = tok.tokenize(text, unitok.configs.english)
    return [token for tag, token in tokens if token.strip()]

def whitespace_tokens(text):

    return text.split()

###
#   For scikit learn
###
def analyzer(token):
    ''' This is used for scikit learn CountVectorizer so that the tokens when
    being analysed are not changed therefore keeping the tokens unmodified
    after being tokenised ourselves.
    '''

    return token

def ngrams(token_list, n_range):
    '''Given a list of tokens will return a list of tokens that have been
    concatenated with the n closests tokens.'''

    def get_n_grams(temp_tokens, n):
        token_copy = list(temp_tokens)
        gram_tokens = []
        while(len(token_copy) >= n):
            n_list = []
            for i in range(0,n):
                n_list.append(token_copy[i])
            token_copy.pop(0)
            gram_tokens.append(' '.join(n_list))
        return gram_tokens

    all_n_grams = []
    for tokens in token_list:
        if n_range == (1,1):
            all_n_grams.append(tokens)
        else:
            all_tokens = []
            for n in range(n_range[0], n_range[1] + 1):
                all_tokens.extend(get_n_grams(tokens, n))
            all_n_grams.append(all_tokens)

    return all_n_grams

###
# Comparison helper to compare predicted values with those submitted
###

def __get_submitted_values():
    early_stop_path = ('Early Stopping',
                       config_path(['submitted_data', 'early_stopping']))
    tweeked_path = ('Tweeked', config_path(['submitted_data', 'tweeked']))

    for sub_name, sub_path in [early_stop_path, tweeked_path]:
        sentiment_values = []
        with open(sub_path, 'r') as fp:
            for data in json.load(fp):
                sentiment_values.append(data['sentiment score'])
        yield sub_name, sentiment_values

def compare(predicted_sentiments):
    '''Given a list or numpy array will return 1 - cosine simlarity between
    the predicted sentiments and those that were submitted to SEMEval this
    is required as the models are not fully reprocible but are very close.

    list of floats -> stdout print message defining ow similar the values
    are to those submitted to SEMEval.
    '''

    for sub_name, sent_values in __get_submitted_values():
        sim_value = 1 - cosine(sent_values, predicted_sentiments)
        msg = ('Similarity between your predicted values and {}: {}'
              ).format(sub_name, sim_value)
        print(msg)

###
#   Training and testing functions
###

def __text_sentiment_company(all_data):
    '''Given a list of dicts will return a tuple of 3 lists containing:
    1. list of strings lower cased - text data
    2. numpy array (len(text data), 1) dimension of floats - sentiment values
    3. list of strings - company names associated to the text data

    list of dicts -> tuple(list of strings, numpy array, list of strings)
    '''

    text = []
    sentiment = []
    company = []
    for data in all_data:
        text.append(data['title'].lower())
        company.append(data['company'].lower())
        # This field does not exist in test dataset
        if 'sentiment' in data:
            sentiment.append(data['sentiment'])
    return text, numpy.asarray(sentiment), company

def fin_data(data_type):
    '''Given either train, trail or test string as data type will retrieve
    those datasets that were given out in SEMEval task 5 track 2 2017 in the
    format of a tuple containing:
    1. list of strings lower cased - text data
    2. numpy array (len(text data), 1) dimension of floats - sentiment values
    3. list of strings - company names associated to the text data

    String -> tuple(list of strings, numpy array, list of strings)
    '''

    data_path = config_path(['data', 'fin_data', data_type + '_data'])
    with open(data_path, 'r') as fp:
        return __text_sentiment_company(json.load(fp))

def fin_word_vector():

    fin_word2vec_path = config_path(['models', 'fin_word2vec'])
    return gensim.models.Word2Vec.load(fin_word2vec_path)

def cosine_score(predicted_values, true_values):
    '''Given two arrays of same length returns the cosine similarity where 1
    is most similar and 0 is not similar.

    list, list -> float
    '''

    return 1 - cosine(predicted_values, true_values)

def stats_report(clf, f_name):
    '''Given a sklearn.model_selection.GridSearchCV it will produce a TSV
    report at f_name stating the different features used and their values and how they
    performed.

    This is useful to determine the best parameters for a model.

    Reference:
    http://scikit-learn.org/stable/auto_examples/model_selection/grid_search_digits.html

    sklearn.model_selection.GridSearchCV, String(file path) -> void
    '''

    def convert_value(value):

        if callable(value):
            value = value.__name__
        return str(value)

    means  = clf.cv_results_['mean_test_score']
    stds   = clf.cv_results_['std_test_score']
    params = clf.cv_results_['params']
    with open(f_name, 'w') as fp:
        fp.write("Mean\tSD\t{} \n".format('\t'.join(params[0].keys())))
        for mean, std, param in zip(means, stds, params):
            param_values = []
            for key, value in param.items():
                if ('__words_replace' in key or '__disimlar' in key or
                    '__word2extract' in key):
                    param_values.append(convert_value(value[0]))
                else:
                    param_values.append(convert_value(value))
            fp.write("{}\t{}\t{}\n".format(str(mean), str(std), '\t'.join(param_values)))

def error_cross_validate(train_data, train_values, model, n_folds=10,
                         shuffle=True, score_function=mean_absolute_error):
    '''Given the training data and true values for that data both a list and
    a model that trains off that data using a fit method it will n_fold
    cross validate off that data and use the models predict function to predict
    each cross validate test data and it will be score using the score_function
    default Mean Absolute Error. The returned value is a list of tuples the first
    value being the index to the data that second value score reprsents.

    returned list of tuples (index, score)
    '''

    results = []

    train_data_array = numpy.asarray(train_data)
    train_values_array = numpy.asarray(train_values)

    kfold = KFold(n_splits=n_folds, shuffle=shuffle)
    for train, test in kfold.split(train_data_array, train_values_array):
        model.fit(train_data_array[train], train_values_array[train])

        predicted_values = model.predict(train_data_array[test])
        real_values = train_values_array[test]

        for i in range(len(predicted_values)):
            pred_value = [predicted_values[i]]
            real_value = [real_values[i]]
            results.append((test[i], pred_value[0],
                            score_function(pred_value, real_value)))
    return results


def top_n_errors(error_res, train_data, train_values, companies, n=10):
    '''Given the output of error_cross_validate it will sort the output (error_res) by
    highest score first and return the top n highest scores data values where the
    data is the train_data and train_values input into error_cross_validate.
    This allows you to find the data that the model most struggled with and tells
    you what it should have been.

    Return sub list of data.
    '''

    error_res = sorted(error_res, key=lambda value: value[2], reverse=True)
    top_errors = error_res[:n]
    return [{'Sentence':train_data[index], 'Company':companies[index],
            'True value':train_values[index], 'Pred value':pred_value,
            'index':index} for index, pred_value, _ in top_errors]

def comps2sent(text_data, companies):
    '''Given the training text data and companies that are the aspect of the sentences
    it returns a dictionary where the keys are the number of companies that are
    mentioned in the sentence and the values are a list of list containg the index
    linking back to the training text data where for that list it will contain
    different id's but be the same sentence. If you perform len on the value of
    the keys it will tell you how many sentences have N amount of companies
    mentioned in the same sentence where N is the key value.

    list of strings, list of strings -> dictionary
    '''

    sentence_compid = {}
    for i in range(len(text_data)):
        text = text_data[i]
        comp = companies[i]
        comps_indexs = sentence_compid.get(text, [])
        comps_indexs.append((comp,i))
        sentence_compid[text] = comps_indexs
    compscount_ids = {}
    for _, compsid in sentence_compid.items():
        ids = compscount_ids.get(len(compsid), [])
        ids.append([comp_id[1] for comp_id in compsid])
        compscount_ids[len(compsid)] = ids
    return compscount_ids

def sent_type_errors(top_errors, compscount_ids):
    '''Given the top  N errors and the number of companies to ids it will return
    the top N errors sorted in a dictionary as the number of companies in the
    sentences and within that the errors. Returns dict.

    List, dict -> dict
    '''

    ids_compscount = {}
    for compscount, ids_list in compscount_ids.items():
        for ids in ids_list:
            for a_id in ids:
                ids_compscount[a_id] = compscount

    comps_errors = {}
    for error in top_errors:
        sent_id = error['index']
        comp_count = ids_compscount[sent_id]
        errors = comps_errors.get(comp_count, [])
        errors.append(error)
        comps_errors[comp_count] = errors
    return comps_errors

def error_analysis(train_data, train_values, train_comps, clf, train_text=False,
                   num_errors=50, n_folds=10, shuffle=True,
                   score_function=mean_absolute_error):
    '''A wrapper function arround the following methods:
    comps2sent
    error_cross_validate
    top_n_errors
    sent_type_errors

    returns tuple of dict, dict
    '''

    compcount_id = None
    if train_text:
        compcount_id = comps2sent(train_text, train_comps)
    else:
        compcount_id = comps2sent(train_data, train_comps)
    error_results = error_cross_validate(train_data, train_values, clf, n_folds=n_folds,
                                         shuffle=shuffle, score_function=score_function)
    top_errors = top_n_errors(error_results, train_data, train_values,
                              train_comps, n=num_errors)
    error_details = sent_type_errors(top_errors, compcount_id)
    error_distribution = {k : len(v) for k, v in error_details.items()}
    return error_details, error_distribution