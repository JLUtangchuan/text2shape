import nrrd
import csv
import pandas as pd
import numpy as np
import collections

import sys
import os

from sklearn.utils import shuffle

from dataloader.TextDataVectorization import TxtVectorization


class TripletShape2Text(object):
    """
    Stores Triples with one shape and a positive and a negative
    matching description
    """

    def __init__(self, shape, pos_desc, neg_desc):
        self.shape = shape
        self.pos_desc = pos_desc
        self.neg_desc = neg_desc


class TripletText2Shape(object):
    """
    Stores Triplets with one description and a negative and positive
    matching shape
    """

    def __init__(self, desc, pos_shape, neg_shape):
        self.desc = desc
        self.pos_shape = pos_shape
        self.neg_shape = neg_shape


class Loader(object):
    """
    Loader class
        tries to load given files
            either primitives ot shapenet data
        handles exceptions
        adds category to shape data
        converts dict{dict{}} to dict{list[]}
        codes all descriptions to vector
    """

    def __init__(self, config):
        if config['dataset'] == "shapenet":
            try:
                self.descriptions = pd.read_csv(
                    config['directories']['train_labels']).to_dict()
            except:
                sys.exit("ERROR! Loader can't load given labels")

            try:
                self.shapes = parse_directory_for_nrrd(
                    config['directories']['train_data'])
            except:
                sys.exit("ERROR! Loader can't load given data")

            self.__add_category_to_shape()
            self.__description_to_lists()

        if config['dataset'] == "primitives":
            try:
                self.shapes, self.descriptions = parse_primitives(
                    config['directories']['primitives'], config['categorize'])
            except:
                sys.exit("ERROR! Loader was not able to parse given directory")
            self.__shuffle_data()

        try:
            self.txt_vectorization = TxtVectorization(
                config['directories']['vocabulary'])
        except:
            sys.exit("ERROR! Loader can't load given vocabulary")

        self.length_voc = len(self.txt_vectorization.voc_list)

        self.__description_to_vector()

    def __add_category_to_shape(self):
        """
        shape is needed for
            calculating the ndcg
            smart batches
        """

        category = list()
        for _, shape_id in enumerate(self.shapes['modelId']):
            cat = "none"
            found_category = False
            for key, value in self.descriptions["modelId"].items():
                if value == shape_id:
                    found_category = True
                    break
            if found_category == True:
                cat = self.descriptions['category'][key]
            category.append(cat)
        self.shapes['category'] = category

    def __description_to_lists(self):
        """
        pandas stores dict within dict which contains idx as key
        this functions converts these dicts into one list
        """

        for key, _ in self.descriptions.items():
            data_list = []
            for _, v in self.descriptions[key].items():
                data_list.append(v)
            self.descriptions[key] = data_list

    def __description_to_vector(self):
        desc_vector_list = list()
        for desc in self.descriptions["description"]:
            desc_vector_list.append(self.txt_vectorization.description2vector(
                desc))
        self.descriptions["description"] = desc_vector_list

    def __shuffle_data(self):
        """
        primitives are sorted -- they need to be shuffled
        TODO:   here just 
                    modelId, description and categrory
                        modelId, data, category
                not other stuff which is stored within desciption dict
        """

        id_shuffled, desc_shuffled, cat_shuffled = shuffle(
            self.descriptions['modelId'], self.descriptions['description'],
            self.descriptions['category'])
        self.descriptions['modelId'] = id_shuffled
        self.descriptions['description'] = desc_shuffled
        self.descriptions['category'] = cat_shuffled

        id_shuffled, data_shuffled, cat_shuffled = shuffle(
            self.shapes['modelId'], self.shapes['data'],
            self.shapes['category'])
        self.shapes['modelId'] = id_shuffled
        self.shapes['data'] = data_shuffled
        self.shapes['category'] = cat_shuffled



class DataLoader(object):
    """
    holds either:
        all data    -->     just retrieval
        train data or
        test data
    """

    def __init__(self, descriptions, shapes):
        self.descriptions = descriptions
        self.shapes = shapes

    def get_shape_length(self):
        return len(self.shapes["modelId"])

    def get_description_length(self):
        return len(self.descriptions["modelId"])

    def get_shape(self, id):
        shape = self.shapes["data"][id]
        shape = np.expand_dims(shape, axis=0)           # bs = 1
        return shape

    def get_description(self, id):
        desc = self.descriptions["description"][id]
        desc = np.expand_dims(desc, axis=0)             # bs = 1
        return desc


class TripletLoader(object):
    """
    uses loader to get all data
    splits data into train and test DataLoader
    generates different triplet batches
    """

    def __init__(self, config):
        loader = Loader(config)

        # TODO: seed to config?
        np.random.seed(1200)

        self.bs = config['hyper_parameters']['bs']
        self.oversample = config['hyper_parameters']['oversample']
        self.txt_vectorization = loader.txt_vectorization
        self.length_voc = len(self.txt_vectorization.voc_list)

        self.__split_train_test(loader)

    def __split_train_test(self, loader):
        """
        split 90/10
        first split shapes
        then look for matching descriptions for shapes and add to corresponding data container
        """

        train_descriptions = {'id': list(), 'modelId': list(), 'description': list(), 'category': list(),
                              'topLevelSynsetId': list(), 'subSynsetId': list()}
        test_descriptions = {'id': list(), 'modelId': list(), 'description': list(), 'category': list(),
                             'topLevelSynsetId': list(), 'subSynsetId': list()}
        train_shapes = dict()
        test_shapes = dict()

        end_train = int(len(loader.shapes['modelId'])*0.9)
        for key, _ in loader.shapes.items():
            d1 = list(loader.shapes[key][:end_train])
            d2 = list(loader.shapes[key][end_train:])
            train_shapes[key] = d1
            test_shapes[key] = d2

        # remember_id is needed for primitives
        #       --> mltiple same shapes and we do not want to
        #           add same description multiple times
        remember_id = []
        for i, shape_id in enumerate(train_shapes['modelId']):
            if shape_id not in remember_id:
                idx = [i for i, x in enumerate(
                    loader.descriptions['modelId']) if x == shape_id]
                for key, val_list in loader.descriptions.items():
                    for id in idx:
                        train_descriptions[key].append(val_list[id])
                remember_id.append(shape_id)

            print("Generate train split {} of {}".format(
                i, len(train_shapes['modelId'])), end='\r')
        print()

        remember_id = []
        for i, shape_id in enumerate(test_shapes['modelId']):
            if shape_id not in remember_id:
                idx = [i for i, x in enumerate(
                    loader.descriptions['modelId']) if x == shape_id]
                for key, val_list in loader.descriptions.items():
                    for id in idx:
                        test_descriptions[key].append(val_list[id])
                remember_id.append(shape_id)

            print("Generate test split {} of {}".format(
                i, len(test_shapes['modelId'])), end='\r')
        print()

        self.train_data = DataLoader(train_descriptions, train_shapes)
        self.test_data = DataLoader(test_descriptions, test_shapes)

    def get_train_batch(self, version):
        batch = []
        if version == "s2t":
            for _ in range(self.bs):
                rand = np.random.randint(0, self.train_data.get_shape_length())
                shape_id = self.train_data.shapes["modelId"][rand]
                shape_category = self.train_data.shapes["category"][rand]
                shape = self.train_data.shapes['data'][rand]

                pos_id = self.__find_positive_description_id(
                    shape_id, data="train")
                # in case of no matching positive description is found
                while pos_id == None:
                    rand = np.random.randint(
                        0, self.train_data.get_shape_length())
                    shape_id = self.train_data.shapes["modelId"][rand]
                    shape = self.train_data.shapes['data'][rand]

                    pos_id = self.__find_positive_description_id(
                        shape_id, data="train")

                pos_desc = self.train_data.descriptions["description"][pos_id]

                neg_id = self.__find_negative_description_id(
                    shape_category, data="train")
                neg_desc = self.train_data.descriptions["description"][neg_id]

                triplet = TripletShape2Text(shape, pos_desc, neg_desc)
                batch.append(triplet)
        if version == "t2s":
            for _ in range(self.bs):
                rand = np.random.randint(
                    0, self.train_data.get_description_length())
                desc_id = self.train_data.descriptions['modelId'][rand]
                desc_category = self.train_data.descriptions['category'][rand]
                desc = self.train_data.descriptions["description"][rand]

                pos_id = self.__find_positive_shape_id(desc_id, "train")

                # in case of no matching positive shape is found
                while pos_id == None:
                    rand = np.random.randint(
                        0, self.train_data.get_description_length())
                    desc_id = self.train_data.descriptions['modelId'][rand]
                    desc = self.train_data.descriptions["description"][rand]

                    pos_id = self.__find_positive_shape_id(
                        desc_id, data="train")

                pos_shape = self.train_data.shapes['data'][pos_id]

                neg_id = self.__find_negative_shape_id(desc_category, data="train")
                neg_shape = self.train_data.shapes['data'][neg_id]

                triplet = TripletText2Shape(desc, pos_shape, neg_shape)
                batch.append(triplet)

        return batch

    def get_test_batch(self, version):
        batch = []
        if version == "s2t":
            for _ in range(self.bs):
                rand = np.random.randint(0, self.test_data.get_shape_length())
                shape_id = self.test_data.shapes["modelId"][rand]
                shape_category = self.test_data.shapes["category"][rand]
                shape = self.test_data.shapes['data'][rand]

                pos_id = self.__find_positive_description_id(
                    shape_id, data="test")
                # in case of no matching positive description is found
                while pos_id == None:
                    rand = np.random.randint(
                        0, self.test_data.get_shape_length())
                    shape_id = self.test_data.shapes["modelId"][rand]
                    shape = self.test_data.shapes['data'][rand]

                    pos_id = self.__find_positive_description_id(
                        shape_id, data="test")

                pos_desc = self.test_data.descriptions["description"][pos_id]

                neg_id = self.__find_negative_description_id(
                    shape_category, data="test")
                neg_desc = self.test_data.descriptions["description"][neg_id]

                triplet = TripletShape2Text(shape, pos_desc, neg_desc)

                batch.append(triplet)
            return batch

        if version == "t2s":
            for _ in range(self.bs):
                rand = np.random.randint(
                    0, self.test_data.get_description_length())
                desc_id = self.test_data.descriptions["modelId"][rand]
                desc_category = self.test_data.descriptions["category"][rand]
                desc = self.test_data.descriptions['description'][rand]

                pos_id = self.__find_positive_shape_id(
                    desc_id, data="test")
                # in case of no matching positive description is found
                while pos_id == None:
                    rand = np.random.randint(
                        0, self.test_data.get_description_length())
                    desc_id = self.test_data.descriptions["modelId"][rand]
                    desc = self.test_data.descriptions['data'][rand]

                    pos_id = self.__find_positive_shape_id(
                        desc_id, data="test")

                pos_shape = self.test_data.shapes["data"][pos_id]

                neg_id = self.__find_negative_shape_id(
                    desc_category, data="test")
                neg_shape = self.test_data.shapes["data"][neg_id]

                triplet = TripletText2Shape(desc, pos_shape, neg_shape)

                batch.append(triplet)
            return batch

    def __find_positive_description_id(self, shape_id, data):
        """
        return random matching idx of all desciptions
        """

        if data == "train":
            matching_idx = [i for i, x in enumerate(
                self.train_data.descriptions['modelId']) if x == shape_id]
            if len(matching_idx) == 0:
                return None
            rand = np.random.randint(0, len(matching_idx))
            return matching_idx[rand]
        if data == "test":
            matching_idx = [i for i, x in enumerate(
                self.test_data.descriptions['modelId']) if x == shape_id]
            if len(matching_idx) == 0:
                return None
            rand = np.random.randint(0, len(matching_idx))
            return matching_idx[rand]

    def __find_negative_description_id(self, shape_category, data):
        if data == "train":
            max_val = len(self.train_data.descriptions["modelId"])
            rand = np.random.randint(0, max_val)
            while self.train_data.descriptions["category"][rand] == shape_category:
                rand = np.random.randint(0, max_val)
            return rand
        if data == "test":
            max_val = len(self.test_data.descriptions["modelId"])
            rand = np.random.randint(0, max_val)
            while self.test_data.descriptions["category"][rand] == shape_category:
                rand = np.random.randint(0, max_val)
            return rand

    def __find_positive_shape_id(self, desc_id, data):
        if data == "train":
            matching_idx = [i for i, x in enumerate(
                self.train_data.shapes['modelId']) if x == desc_id]
            if len(matching_idx) == 0:
                return None
            rand = np.random.randint(0, len(matching_idx))
            return matching_idx[rand]
        if data == "test":
            matching_idx = [i for i, x in enumerate(
                self.test_data.shapes['modelId']) if x == desc_id]
            if len(matching_idx) == 0:
                return None
            rand = np.random.randint(0, len(matching_idx))
            return matching_idx[rand]

    def __find_negative_shape_id(self, desc_category, data):
        if data == "train":
            max_val = len(self.train_data.shapes["modelId"])
            rand = np.random.randint(0, max_val)
            while self.train_data.shapes["category"][rand] == desc_category:
                rand = np.random.randint(0, max_val)
            return rand
        if data == "test":
            max_val = len(self.test_data.shapes["modelId"])
            rand = np.random.randint(0, max_val)
            while self.test_data.shapes["category"][rand] == desc_category:
                rand = np.random.randint(0, max_val)
            return rand

    def get_train_smart_batch(self, version):
        """
        return batch of similar descriptions selected from bs*oversample 
        weighted according to frequency of word in selection
        """

        randID = np.random.randint(
            0, self.train_data.get_shape_length(), self.bs*self.oversample)
        pos_descriptions = []

        for i, index in enumerate(randID):
            shape_id = self.train_data.shapes["modelId"][index]
            pos_id = self.__find_positive_description_id(
                shape_id, data="train")
            # in case of no matching positive description is found
            # workaround for descriptions without shape
            while pos_id == None:
                temp = np.random.randint(0, self.train_data.get_shape_length())
                shape_id = self.train_data.shapes["modelId"][temp]
                pos_id = self.__find_positive_description_id(
                    shape_id, data="train")
                randID[i] = temp
            pos_descriptions.append(
                self.train_data.descriptions["description"][pos_id])

        # flattens list
        all_pos_desc = [
            item for sublist in pos_descriptions for item in sublist]
        # remove all zeros
        all_pos_desc = list(filter(lambda a: a != 0, all_pos_desc))
        occurrences = collections.Counter(all_pos_desc)

        scores = []
        for description in pos_descriptions:
            scores.append(self.comp_desc(
                pos_descriptions[0], description, occurrences))

        sorted_idx = np.argsort(scores)[::-1]  # sort ascending order
        self.selected_ids = np.array(randID)[sorted_idx[:self.bs]].tolist()

        batch = []
        if version == "s2t":
            for index in self.selected_ids:
                shape = self.train_data.shapes['data'][index]
                shape_id = self.train_data.shapes["modelId"][index]
                pos_id = self.__find_positive_description_id(
                    shape_id, data="train")
                pos_desc = self.train_data.descriptions["description"][pos_id]

                neg_id = self.__find_smart_negative_description_id(
                    shape_id, data="train")
                neg_desc = self.train_data.descriptions["description"][neg_id]

                triplet = TripletShape2Text(shape, pos_desc, neg_desc)
                batch.append(triplet)

            return batch

        if version == "t2s":
            for index in self.selected_ids:
                pos_shape = self.train_data.shapes['data'][index]
                shape_id = self.train_data.shapes["modelId"][index]
                pos_id = self.__find_positive_description_id(
                    shape_id, data="train")
                desc = self.train_data.descriptions["description"][pos_id]

                neg_id = self.__find_smart_negative_shape_id(
                    shape_id, data="train")
                neg_shape = self.train_data.shapes['data'][neg_id]

                triplet = TripletText2Shape(desc, pos_shape, neg_shape)
                batch.append(triplet)

            return batch

    def get_test_smart_batch(self, version):
        randID = np.random.randint(
            0, self.test_data.get_shape_length(), self.bs*self.oversample)
        pos_descriptions = []

        for i, index in enumerate(randID):
            shape_id = self.test_data.shapes["modelId"][index]
            pos_id = self.__find_positive_description_id(shape_id, data="test")
            # in case of no matching positive description is found
            # workaround for descriptions without shape
            while pos_id == None:
                temp = np.random.randint(0, self.test_data.get_shape_length())
                shape_id = self.test_data.shapes["modelId"][temp]
                pos_id = self.__find_positive_description_id(
                    shape_id, data="test")
                randID[i] = temp
            pos_descriptions.append(
                self.test_data.descriptions["description"][pos_id])

        # flattens list
        all_pos_desc = [
            item for sublist in pos_descriptions for item in sublist]
        # remove all zeros
        all_pos_desc = list(filter(lambda a: a != 0, all_pos_desc))
        occurrences = collections.Counter(all_pos_desc)

        scores = []
        for description in pos_descriptions:
            scores.append(self.comp_desc(
                pos_descriptions[0], description, occurrences))

        sorted_idx = np.argsort(scores)[::-1]  # sort ascending order
        self.selected_ids = np.array(randID)[sorted_idx[:self.bs]].tolist()

        batch = []
        if version == "s2t":
            for index in self.selected_ids:
                shape = self.test_data.shapes['data'][index]
                shape_id = self.test_data.shapes["modelId"][index]
                pos_id = self.__find_positive_description_id(
                    shape_id, data="test")
                pos_desc = self.test_data.descriptions["description"][pos_id]

                neg_id = self.__find_smart_negative_description_id(
                    shape_id, data="test")
                neg_desc = self.test_data.descriptions["description"][neg_id]

                triplet = TripletShape2Text(shape, pos_desc, neg_desc)
                batch.append(triplet)

            return batch

        if version == "t2s":
            for index in self.selected_ids:
                pos_shape = self.test_data.shapes['data'][index]
                shape_id = self.test_data.shapes["modelId"][index]
                pos_id = self.__find_positive_description_id(
                    shape_id, data="test")
                desc = self.test_data.descriptions["description"][pos_id]

                neg_id = self.__find_smart_negative_shape_id(
                    shape_id, data="test")
                neg_shape = self.test_data.shapes['data'][neg_id]

                triplet = TripletText2Shape(desc, pos_shape, neg_shape)
                batch.append(triplet)

            return batch

    def comp_desc(self, original, new, weights=None):
        intersection = set(original).intersection(new)

        if weights == None:
            return len(intersection)
        else:
            weighted_matches = 0
            for each in intersection:
                weighted_matches += weights[each]
            return weighted_matches

    def __find_smart_negative_description_id(self, shape_id, data):
        """
        return  matching idx of close descriptions
        """

        if data == "train":
            rand = np.random.randint(0, self.bs)
            index = self.selected_ids[rand]
            while self.train_data.descriptions["modelId"][index] == shape_id:
                rand = np.random.randint(0, self.bs)
                index = self.selected_ids[rand]
            return index
        if data == "test":
            rand = np.random.randint(0, self.bs)
            index = self.selected_ids[rand]
            while self.test_data.descriptions["modelId"][index] == shape_id:
                rand = np.random.randint(0, self.bs)
                index = self.selected_ids[rand]
            return index

    def __find_smart_negative_shape_id(self, shape_id, data):
        if data == "train":
            rand = np.random.randint(0, self.bs)
            index = self.selected_ids[rand]
            while self.train_data.shapes["modelId"][index] == shape_id:
                rand = np.random.randint(0, self.bs)
                index = self.selected_ids[rand]
            return index

        if data == "test":
            rand = np.random.randint(0, self.bs)
            index = self.selected_ids[rand]
            while self.test_data.shapes["modelId"][index] == shape_id:
                rand = np.random.randint(0, self.bs)
                index = self.selected_ids[rand]
            return rand


class RetrievalLoader(DataLoader):
    """
    holds all data
    """

    def __init__(self, config):
        loader = Loader(config)
        super(RetrievalLoader, self).__init__(
            loader.descriptions, loader.shapes)

        self.txt_vectorization = loader.txt_vectorization
        self.length_voc = len(self.txt_vectorization.voc_list)


def parse_directory_for_nrrd(path):
    shapes = dict()
    shapes['modelId'] = []
    shapes['data'] = []
    i = 0
    for root, _, files in os.walk(path):
        for file in files:
            if file.endswith(".nrrd"):
                train_data, _ = nrrd.read(
                    os.path.join(root, file), index_order='C')
                shapes['modelId'].append(file.replace('.nrrd', ''))
                shapes['data'].append(train_data)

        print("parse directory {}".format(
            i), end='\r')
        i += 1

    return shapes


def parse_primitives(path, categorize):
    """
    generates needed form for training from
    all files given in primitives directory
    each folder contains:
        10 shapes
        between 20 and a few hunded descriptions
    """

    shapes = dict()
    shapes['modelId'] = []
    shapes['data'] = []
    shapes['category'] = []
    descriptions = dict()
    descriptions['modelId'] = []
    descriptions['description'] = []
    descriptions['category'] = []

    for root, _, files in os.walk(path):
        # used later to share descriptions between shapes
        name_list = []
        cat_list = []
        desc_list = []
        for file in files:
            if file.endswith(".nrrd"):
                name = file.replace(".nrrd", '')
                name_list.append(name)
                splitted = name.split("-")
                if categorize == "shape_color":
                    category = splitted[0] + " " + splitted[1]
                if categorize == "shape":
                    category = splitted[0]
                    
                cat_list.append(category)
                train_data, _ = nrrd.read(
                    os.path.join(root, file), index_order='C')
                shapes['modelId'].append(name)
                shapes['data'].append(train_data)
                shapes['category'].append(category)

            if file.endswith(".txt"):
                # either too stupid or pandas suchs in this case
                with open(os.path.join(root, file), newline='') as f:
                    reader = csv.reader(f)
                    desc_list = list(reader)
        
        # share the descriptions across shapes
        if len(desc_list) != 0:
            for desc in desc_list:
                choice = np.random.randint(0, len(name_list))
                descriptions['modelId'].append(name_list[choice])
                descriptions['description'].append(desc[0])
                descriptions['category'].append(cat_list[choice])

    return shapes, descriptions
