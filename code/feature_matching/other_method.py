# coding: utf-8

# In[1]:

# Load libraries
import time
from multiprocessing.pool import Pool
import pickle
from pandas import read_csv
from nltk.corpus import wordnet as wn
from nltk.corpus import brown
import math
import nltk
import sys
from nltk.corpus import stopwords
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
import re
# from xgboost import XGBClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score

# In[3]:


ALPHA = 0.2
BETA = 0.45
ETA = 0.4
PHI = 0.2
DELTA = 0.85

brown_freqs = dict()
N = 0


# In[8]:

######################### word similarity ##########################
def get_best_synset_pair(word_1, word_2):
    max_sim = -1.0
    synsets_1 = wn.synsets(word_1)
    synsets_2 = wn.synsets(word_2)
    if len(synsets_1) == 0 or len(synsets_2) == 0:
        return None, None
    else:
        max_sim = -1.0
        best_pair = None, None
        for synset_1 in synsets_1:
            for synset_2 in synsets_2:
                sim = wn.path_similarity(synset_1, synset_2)
                if sim != None and sim > max_sim:
                    max_sim = sim
                    best_pair = synset_1, synset_2
        return best_pair


def length_dist(synset_1, synset_2):
    l_dist = sys.maxsize
    if synset_1 is None or synset_2 is None:
        return 0.0
    if synset_1 == synset_2:
        # if synset_1 and synset_2 are the same synset return 0
        l_dist = 0.0
    else:
        wset_1 = set([str(x.name()) for x in synset_1.lemmas()])
        wset_2 = set([str(x.name()) for x in synset_2.lemmas()])
        if len(wset_1.intersection(wset_2)) > 0:
            # if synset_1 != synset_2 but there is word overlap, return 1.0
            l_dist = 1.0
        else:
            # just compute the shortest path between the two
            l_dist = synset_1.shortest_path_distance(synset_2)
            if l_dist is None:
                l_dist = 0.0
    # normalize path length to the range [0,1]
    return math.exp(-ALPHA * l_dist)


def hierarchy_dist(synset_1, synset_2):
    h_dist = sys.maxsize
    if synset_1 is None or synset_2 is None:
        return h_dist
    if synset_1 == synset_2:
        # return the depth of one of synset_1 or synset_2
        h_dist = max([x[1] for x in synset_1.hypernym_distances()])
    else:
        # find the max depth of least common subsumer
        hypernyms_1 = {x[0]: x[1] for x in synset_1.hypernym_distances()}
        hypernyms_2 = {x[0]: x[1] for x in synset_2.hypernym_distances()}
        lcs_candidates = set(hypernyms_1.keys()).intersection(
            set(hypernyms_2.keys()))
        if len(lcs_candidates) > 0:
            lcs_dists = []
            for lcs_candidate in lcs_candidates:
                lcs_d1 = 0
                if lcs_candidate in hypernyms_1:
                    lcs_d1 = hypernyms_1[lcs_candidate]
                lcs_d2 = 0
                if lcs_candidate in hypernyms_2:
                    lcs_d2 = hypernyms_2[lcs_candidate]
                lcs_dists.append(max([lcs_d1, lcs_d2]))
            h_dist = max(lcs_dists)
        else:
            h_dist = 0
    return ((math.exp(BETA * h_dist) - math.exp(-BETA * h_dist)) /
            (math.exp(BETA * h_dist) + math.exp(-BETA * h_dist)))


def word_similarity(word_1, word_2):
    synset_pair = get_best_synset_pair(word_1, word_2)
    return (length_dist(synset_pair[0], synset_pair[1]) *
            hierarchy_dist(synset_pair[0], synset_pair[1]))


######################### sentence similarity ##########################

def most_similar_word(word, word_set):
    max_sim = -1.0
    sim_word = ""
    for ref_word in word_set:
        sim = word_similarity(word, ref_word)
        if sim > max_sim:
            max_sim = sim
            sim_word = ref_word
    return sim_word, max_sim


def info_content(lookup_word):
    global N
    if N == 0:
        # poor man's lazy evaluation
        for sent in brown.sents():
            for word in sent:
                word = word.lower()
                if word not in brown_freqs:
                    brown_freqs[word] = 0
                brown_freqs[word] = brown_freqs[word] + 1
                N = N + 1
    lookup_word = lookup_word.lower()
    n = 0 if lookup_word not in brown_freqs else brown_freqs[lookup_word]
    return 1.0 - (math.log(n + 1) / math.log(N + 1))


def semantic_vector(words, joint_words, info_content_norm):
    sent_set = set(words)
    semvec = np.zeros(len(joint_words))
    i = 0
    for joint_word in joint_words:
        if joint_word in sent_set:
            # if word in union exists in the sentence, s(i) = 1 (unnormalized)
            semvec[i] = 1.0
            if info_content_norm:
                semvec[i] = semvec[i] * math.pow(info_content(joint_word), 2)
        else:
            # find the most similar word in the joint set and set the sim value
            sim_word, max_sim = most_similar_word(joint_word, sent_set)
            semvec[i] = PHI if max_sim > PHI else 0.0
            if info_content_norm:
                semvec[i] = semvec[i] * info_content(joint_word) * info_content(sim_word)
        i = i + 1
    return semvec


def semantic_similarity(sentence_1, sentence_2):
    #     sentence_1 = re.sub('[^A-Za-z0-9\s]', '', row['question1']).lower()
    #     sentence_2 = re.sub('[^A-Za-z0-9\s]', '', row['question2']).lower()
    info_content_norm = True
    words_1 = nltk.word_tokenize(sentence_1)
    words_2 = nltk.word_tokenize(sentence_2)
    joint_words = set(words_1).union(set(words_2))
    vec_1 = semantic_vector(words_1, joint_words, info_content_norm)
    vec_2 = semantic_vector(words_2, joint_words, info_content_norm)
    return np.dot(vec_1, vec_2.T) / (np.linalg.norm(vec_1) * np.linalg.norm(vec_2))


# In[9]:

######################### word order similarity ##########################

def word_order_vector(words, joint_words, windex):
    wovec = np.zeros(len(joint_words))
    i = 0
    wordset = set(words)
    for joint_word in joint_words:
        if joint_word in wordset:
            # word in joint_words found in sentence, just populate the index
            wovec[i] = windex[joint_word]
        else:
            # word not in joint_words, find most similar word and populate
            # word_vector with the thresholded similarity
            sim_word, max_sim = most_similar_word(joint_word, wordset)
            if max_sim > ETA:
                wovec[i] = windex[sim_word]
            else:
                wovec[i] = 0
        i = i + 1
    return wovec


def word_order_similarity(sentence_1, sentence_2):
    words_1 = nltk.word_tokenize(sentence_1)
    words_2 = nltk.word_tokenize(sentence_2)
    joint_words = list(set(words_1).union(set(words_2)))
    windex = {x[1]: x[0] for x in enumerate(joint_words)}
    r1 = word_order_vector(words_1, joint_words, windex)
    r2 = word_order_vector(words_2, joint_words, windex)
    return 1.0 - (np.linalg.norm(r1 - r2) / np.linalg.norm(r1 + r2))


# In[10]:

def similarity(sentence_1, sentence_2):
    return DELTA * semantic_similarity(sentence_1, sentence_2) + (1.0 - DELTA) * word_order_similarity(sentence_1,
                                                                                                       sentence_2)


# In[21]:

######################### tf-idf measures ##########################

def tfidf_vector_similarity(sentence_1, sentence_2):
    corpus = [sentence_1, sentence_2]
    vectorizer = TfidfVectorizer(min_df=1)
    vec_1 = vectorizer.fit_transform(corpus).toarray()[0]
    vec_2 = vectorizer.fit_transform(corpus).toarray()[1]
    sim = np.dot(vec_1, vec_2.T) / (np.linalg.norm(vec_1) * np.linalg.norm(vec_2))
    return sim


# In[20]:

######################### word overlap measures ##########################

def jaccard_similarity_coefficient(sentence_1, sentence_2):
    words_1 = nltk.word_tokenize(sentence_1)
    words_2 = nltk.word_tokenize(sentence_2)
    joint_words = set(words_1).union(set(words_2))
    intersection_words = set(words_1).intersection(set(words_2))
    return len(intersection_words) / len(joint_words)

# In[26]:
def get_end_data(a):
    tmp = set([i[0] for i in a])
    dic = {}
    for i in tmp:
        dic[i] = []
    for i,j,z in a:
        dic[i].append([i,j,z])
    for i in dic.keys():
        dic[i] = max(dic[i],key=lambda x: x[-1])
    end = list(dic.values())
    end.sort(key=lambda x:x[-1],reverse=True)
    return end
def word2(i):
    (x,y) = i
    sim = semantic_similarity(x,y)
    return [i[0],i[1],sim]


def get_list(get_phrase1,get_phrase2):
    arr = []
    for i in get_phrase1:
        for j in get_phrase2:
            arr.append((i,j))
    return arr

def clac1(s1,s2,method=1):
    arr = []
    for i in s1:
        for j in s2:
            if method==2:
                max_tmp = jaccard_similarity_coefficient(i, j)
                arr.append([i, j, max_tmp])
            else:

                max_tmp = tfidf_vector_similarity(i,j)
                arr.append([i,j,max_tmp])
    return arr
def write_to_csv(data,filename):
    with open(filename,'w') as f:
        for i in data:
            f.write('"{}","{}",{}\n'.format(i[0],i[1],i[2]))
    return None

def cal_jk(s1,s2):
    all_list = []
    for i in s1:
        max_j = []
        for j in s2:
            sim = jaccard_similarity_coefficient(i,j)
            max_j.append([i, j, sim])
        all_list.append(max(max_j, key=lambda x: x[-1]))
    return all_list
def cal_tfidf(s1,s2):
    all_list = []
    for i in s1:
        max_j = []
        for j in s2:
            sim = tfidf_vector_similarity(i,j)
            max_j.append([i, j, sim])
        all_list.append(max(max_j, key=lambda x: x[-1]))
    return all_list

def cal_wordnet(s1,s2):
    all_list = []
    for i in s1:
        max_j = []
        for j in s2:
            sim = similarity(i,j)
            max_j.append([i, j, sim])
        all_list.append(max(max_j, key=lambda x: x[-1]))
    return all_list
# a = [ 'Instagram_privacy_reviews', 'Spotify_privacy_reviews', 'TikTok_privacy_reviews',
#      'Twitter_privacy_reviews',
#      'YouTube_privacy_reviews']
# for i in a:
#     data = pickle.load(open('./pk2/{}.pk'.format(i), 'rb'))
#     s1 = data['s1']
#     s2 = data['s2']
#     arr = cal_wordnet(s1, s2)
#     with open('./wordnet/{}-wn.csv'.format(i), 'w') as f:
#         for (i, j, z), id in zip(arr, data['id']):
#             z = str(z)
#             f.write('"{}","{}",{},{}'.format(i, j, z, id) + '\n')
if __name__ == '__main__':
    print('*'*50)
    data = pickle.load(open('./pk2/{}.pk'.format('YouTube_privacy_reviews'), 'rb'))
    s1 = data['s1']
    s2 = data['s2']
    fiter = ['have the video','shoot','watch']
    s2 = [i.replace('watch engage','engage') for i in s2 if i not in fiter]
    s2 = [i.replace('the youtube ','').replace('youtube ','') for i in s2]
    arr = cal_tfidf(s1, s2)
    with open('{}-tfidf.csv'.format('YouTube_privacy_reviews'), 'w') as f:
        for (i, j, z), id in zip(arr, data['id']):
            z = str(z)
            f.write('"{}","{}",{},{}'.format(i, j, z, id) + '\n')