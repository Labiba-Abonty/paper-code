

import gensim
import numpy as np
from itertools import product
from multiprocessing import Pool
from sematch.semantic.similarity import WordNetSimilarity



def wn_sim(phrasePair):
	phrase1, phrase2 = phrasePair
	distance = 0.0
	count = 0.0
	for w1, w2 in product(phrase1, phrase2):
		if set((w1, w2)).__len__() != 1:
			score = wns.word_similarity(w1, w2, 'wpath')
			distance += (1 - score)
			count += 1
	return distance / count


def wv_sim(phrasePair):
	phrase1, phrase2 = phrasePair
	distance = 0.0
	count = 0.0
	for w1, w2 in product(phrase1, phrase2):
		if set((w1, w2)).__len__() != 1:
			score = wv.similarity(w1, w2)
			distance += (1 - score)
			count += 1
	return distance / count


def pairwise_wv_sim(phrasePairs):
	global wv
	wv = gensim.models.KeyedVectors.load("/home/zjz/Desktop/vec.pkl")
	pool = Pool(processes=4)
	dis_list = pool.map(wv_sim, phrasePairs)
	return np.asarray(dis_list, dtype=float)


def pairwise_wn_sim(phrasePairs):
	global wns
	wns = WordNetSimilarity()
	pool = Pool(processes=4)
	dis_list = pool.map(wn_sim, list(phrasePairs))
	return np.asarray(dis_list, dtype=float)



