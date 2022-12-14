'''
This file is used to BIO tagging on the pure texts for the modelB, which covers information including salutation,
party, state, county, and city. The output file will be in the format of spaCy Doc file.

The output file will be in the format of spaCy Doc file.

special tricks applied: 
1. use the external file that stores the US states information to tag the abbreviation and full name of the state information.
    the abbreviation will be tagged as "STATE", and the full name will be tagged as "STATE_F".

special dependencies:
1. the `state.csv` file that stores the US states information.

'''

import argparse
import collections
import json
import os
import re
from pathlib import Path

import pandas as pd
import spacy
from sklearn.model_selection import train_test_split
from spacy.tokens import Doc, DocBin
from spacy.util import filter_spans
from tqdm import tqdm


def get_parser(parser=argparse.ArgumentParser(
    description='to BIO tagging on the pure texts for the modelB, '
    'which covers information including salutation, party, state, county, and city. '
    'The output file will be in the format of spaCy Doc file.'),):
    parser.add_argument(
        "--input_json",
        type=str,
        default="data.json",
        help="the input json file that stores the pure texts of the webpages",
    )
    parser.add_argument(
        "--input_csv",
        type=str,
        default="data.csv",
        help="the input csv file that stores the Cicero dataset",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default="mergeB_data",
        help="the output directory that stores the tagged dataset",
    )
    parser.add_argument(
        "--state",
        type=str,
        default="state.csv",
        help="the external file that stores the US states information",
    )
    parser.add_argument(
        "--ratio",
        type=float,
        default=0.1,
        help="the ratio of the dev set",
    )
    return parser


def bio_tag(args):
    # detect if the output directory exists
    if not os.path.exists(args.output):
        os.makedirs(args.output)

    # load the Cicero dataset
    cicero_df = pd.read_csv(args.input_csv, error_bad_lines=False)

    # load the pure texts of the webpages
    with open(args.input_json, "r") as f:
        pure_text_dict = json.load(f)

    # load the external file that stores the US states information
    state_df = pd.read_csv(args.state)
    state_abbr = state_df["Abbreviation"].tolist()
    state_full = state_df["Full-Name"].tolist()
    state_dict = dict(zip(state_abbr, state_full))

    nlp = spacy.load('en_core_web_sm')
    # bio tagging
    # the output will be stored in the list first and then save as the spaCy Doc file
    tagged_data = []

    for n in tqdm(range(len(cicero_df))):
        information_unit = cicero_df.iloc[n].dropna()
        politician_id = information_unit["id"]

        pure_text = pure_text_dict.get(str(politician_id), None)

        # skip the data point that we cannot find the pure text due to some reasons
        # for example, the url address is not valid
        if pure_text is None:
            continue

        ruler = nlp.add_pipe("span_ruler")
        bio_tag_pattern_list = []

        # reference: https://spacy.io/usage/rule-based-matching
        if "salutation" in information_unit.keys():
            salutation = information_unit["salutation"]
            bio_tag_pattern_list.append({
                "label": "SALUTATION",
                "pattern": salutation
            })

        if "party" in information_unit.keys():
            party = information_unit["party"]
            bio_tag_pattern_list.append({"label": "PARTY", "pattern": party})

        if "primary_state" in information_unit.keys():
            state = information_unit["primary_state"]
            bio_tag_pattern_list.append({"label": "STATE", "pattern": state})
            # get the full name of the state
            if state in state_abbr:
                state_full_name = state_dict[state]
                bio_tag_pattern_list.append({
                    "label": 'STATE_F',
                    'pattern': [{
                        'LOWER': state_full_name.lower()
                    }]
                })

        if "secondary_state" in information_unit.keys():
            state = information_unit["secondary_state"]
            bio_tag_pattern_list.append({"label": "STATE", "pattern": state})
            # get the full name of the state
            if state in state_abbr:
                state_full_name = state_dict[state]
                bio_tag_pattern_list.append({
                    "label": 'STATE_F',
                    'pattern': [{
                        'LOWER': state_full_name.lower()
                    }]
                })

        if "primary_county" in information_unit.keys():
            county = information_unit["primary_county"]
            bio_tag_pattern_list.append({"label": "COUNTY", "pattern": county})

        if "secondary_county" in information_unit.keys():
            county = information_unit["secondary_county"]
            bio_tag_pattern_list.append({"label": "COUNTY", "pattern": county})

        if "primary_city" in information_unit.keys():
            city = information_unit["primary_city"]
            bio_tag_pattern_list.append({"label": "CITY", "pattern": city})

        if "secondary_city" in information_unit.keys():
            city = information_unit["secondary_city"]
            bio_tag_pattern_list.append({"label": "CITY", "pattern": city})

        ruler.add_patterns(bio_tag_pattern_list)
        doc = nlp(pure_text)
        # split the doc into multiple chunks since the input of the model should be
        # less than 512 tokens
        length = len(doc) // 100
        for n in range(length + 1):
            sub_doc = nlp(str(doc[n * 100:(n + 1) * 100]))
            # the filter_spans function is used to remove the overlapping entities
            sub_doc.ents = filter_spans(sub_doc.spans["ruler"])
            tagged_data.append(sub_doc)

        # remove the ruler and initialize a new one for each politician/data point
        nlp.remove_pipe("span_ruler")

    # remove the empty data point
    tagged_data = [doc for doc in tagged_data if len(doc) > 0]

    # split the tagged data into training set and test set
    train, dev = train_test_split(tagged_data,
                                  test_size=args.ratio,
                                  random_state=42)

    train_db = DocBin()
    for n in train:
        train_db.add(n)
    train_db.to_disk(args.output / "train.spacy")

    dev_db = DocBin()
    for n in dev:
        dev_db.add(n)
    dev_db.to_disk(args.output / "dev.spacy")


if __name__ == "__main__":
    args = get_parser().parse_args()
    bio_tag(args)
