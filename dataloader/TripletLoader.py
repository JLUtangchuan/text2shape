import torch.utils.data as data
import nrrd
import pandas as pd
import numpy as np
import random

import sys
import os

from dataloader.TextDataVectorization import TxtVectorization

class Triplet(object):
    def __init__(self, shape, pos_desc, neg_desc):
        self.shape = shape
        self.pos_desc = pos_desc
        self.neg_desc = neg_desc


class TripletLoader(data.Dataset):
    '''
    loads all data and generates triplets:
        Anchor shape
        Positive description vector
        Negative description vector
    all triplets are saved within list self.triplets    
    random batch gets generated from self.triplets
    '''

    def __init__(self, config):
        self.bs = config['hyper_parameters']['bs']

        try:
            self.descriptions = pd.read_csv(
                config['directories']['train_labels']).to_dict()
        except:
            sys.exit("ERROR! Triplet loader can't load given labels")

        try:
            self.shapes = parse_directory_for_nrrd(
                config['directories']['train_data'])
            #self.train_data, _ = nrrd.read(config['directories']['train_data'], index_order = 'C')
        except:
            sys.exit("ERROR! Triplet loader can't load given data")

        try:
            self.txt_vectorization = TxtVectorization(config['directories']['vocabulary'])
        except:
            sys.exit("ERROR! Triplet loader can't load given vocabulary")        

        self.triplet_list = []
        self.triplet_train = []
        self.triplet_test = []
        self.length_voc = len(self.txt_vectorization.voc_list)

        # TODO: seed to config?
        np.random.seed(1200)

        self.generate_triplets()

        if self.__len__() == 0:
            raise("ERROR! No triplets loaded!")
        
        self.split_train_test()

    def __getitem__(self, index):
        # TODO:
        print("HUi")

    def __len__(self):
        return len(self.triplet_list)
    
    def get_length(self, mode):
        if mode == "train":
            return len(self.triplet_train)
        if mode == "test":
            return len(self.triplet_test)

    def generate_triplets(self):
        for i in range(len(self.shapes["modelId"])):
            shape_id = self.shapes["modelId"][i]
            pos_idx = self.find_positive_description_idx(shape_id)
            for pos_id in pos_idx:
                shape = self.shapes["data"][i]

                pos_desc = self.descriptions["description"][pos_id]
                pos_desc = self.txt_vectorization.description2vector(pos_desc)

                neg_id = self.find_negative_desciption_id(shape_id)
                neg_desc = self.descriptions["description"][neg_id]
                neg_desc = self.txt_vectorization.description2vector(neg_desc)

                triplet = Triplet(shape, pos_desc, neg_desc)
                self.triplet_list.append(triplet)
            print('Generating triplet list {:.2f} %'.format(
                i/len(self.shapes["modelId"])*100), end='\r')
        print("Finished generating triplet list :)")

    def find_positive_description_idx(self, shape_id):
        matching_idx = []
        for key, value in self.descriptions["modelId"].items():
            if value == shape_id:
                matching_idx.append(key)
        return matching_idx

    def find_negative_desciption_id(self, shape_id):
        max_val = len(self.descriptions["modelId"])
        rand = np.random.randint(0, max_val)
        while self.descriptions["modelId"][rand] == shape_id:
            rand = np.random.randint(0, max_val)
        return rand

    def split_train_test(self):
        '''
        split 80/20 pareto ratio
        '''
        random.shuffle(self.triplet_list)
        end_train = int(self.__len__()*0.8)
        self.triplet_train = self.triplet_list[:end_train]
        self.triplet_test = self.triplet_list[end_train:]

    def get_batch(self, mode):
        batch = []
        for i in range(self.bs):
            if mode == "train":
                rand = np.random.randint(0, len(self.triplet_train))
                batch.append(self.triplet_train[rand])
            if mode == "test":
                rand = np.random.randint(0, len(self.triplet_test))
                batch.append(self.triplet_test[rand])
        return batch


def parse_directory_for_nrrd(path):
    shapes = dict()
    shapes['modelId'] = []
    shapes['data'] = []
    file_list = []
    for root, dirs, files in os.walk(path):
        for file in files:
            if file.endswith(".nrrd"):
                train_data, _ = nrrd.read(
                    os.path.join(root, file), index_order='C')
                shapes['modelId'].append(file.replace('.nrrd', ''))
                shapes['data'].append(train_data)

    return shapes
