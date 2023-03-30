import copy
import pickle
import os
import json
from timeit import timeit
from typing import List

import matplotlib.pyplot as plt
from matplotlib.cm import get_cmap
import thefuzz.process
from tqdm import tqdm
import numpy as np
import pandas as pd

from sabrosa_backend.util import project_path

# load and setup data
food_df = pd.read_csv(os.path.join(project_path, "shortened_food.csv"))
use_fdc_ids = food_df['fdc_id'].tolist()
nutrient_df = pd.read_csv(os.path.join(project_path, "nutrient.csv"))
nutrient_df = nutrient_df[nutrient_df['fdc_id'].isin(use_fdc_ids)]
food_df = food_df.sort_values(['fdc_id'])
nutrient_df = nutrient_df.sort_values(['fdc_id', 'nutrient_id'])
nutrient_definitions = json.load(
    open(os.path.join(project_path, "nutrient_definitions.json")))
intake_profiles = json.load(
    open(os.path.join(project_path, "intake_profiles.json")))
global_uls = json.load(open(os.path.join(project_path, "global_uls.json")))
intake_profile_mapping = json.load(
    open(os.path.join(project_path, "intake_profile_mapping.json")))
reversed_intake_profile_mapping = {
    v: k
    for k, v in intake_profile_mapping.items()
}
nutrient_definitions = sorted(nutrient_definitions, key=lambda x: x['id'])
master_food_nutrient_amounts = []

for fdc_id, group in nutrient_df.groupby('fdc_id'):
  master_food_nutrient_amounts.append(group['amount_per_100g'].values)

master_food_nutrient_amounts = np.array(master_food_nutrient_amounts)

from transformers import AutoTokenizer, AutoModel

tokenizer = AutoTokenizer.from_pretrained(
    "sentence-transformers/paraphrase-MiniLM-L3-v2")
model = AutoModel.from_pretrained(
    "sentence-transformers/paraphrase-MiniLM-L3-v2")

index_strings = (food_df['shortened_name'] + " " + food_df['emojis']).tolist()
index_strings = [str(s) for s in index_strings]
embeds = []
for b_i in tqdm(range(len(index_strings) // 32 + 1)):
  start = b_i * 32
  end = min([len(index_strings), (b_i + 1) * 32])
  if start < end:
    these_embeds = model(**tokenizer.batch_encode_plus(
        index_strings[start:end], return_tensors="pt",
        padding=True)).pooler_output.detach().numpy()
    embeds.append(these_embeds)

search_index = np.concatenate(embeds, axis=0)


class Food:
  def __init__(self, fdc_id, amount, name, nutrients):
    self.fdc_id = fdc_id
    self.amount = amount
    self.name = name
    self.nutrients = nutrients

  @staticmethod
  def from_fdc_id(fdc_id, amount: float):
    relevant_food = food[food['fdc_id'] == fdc_id].iloc[0]
    # nutrient_rows = nutrient[nutrient['fdc_id'] == fdc_id]
    nutrient_rows = food_nutrients_map[fdc_id]
    nutrient_objects = []
    for i, n_def in enumerate(nutrient_definitions):
      relevant_nutrient = nutrient_rows.iloc[i]
      assert relevant_nutrient['nutrient_id'] == n_def['id']
      nutrient_objects.append({
          'name':
          n_def['name'],
          'amount':
          relevant_nutrient['amount_per_100g'] / 100 * amount,
          'id':
          n_def['id'],
          'unit':
          n_def['unitName']
      })
    return Food(fdc_id,
                amount=amount,
                name=relevant_food['name'],
                nutrients=nutrient_objects)

  def macro_ratio(self):
    water = [n for n in self.nutrients if n['id'] == 255][0]['amount_per_100g']
    protein = [n for n in self.nutrients
               if n['id'] == 203][0]['amount_per_100g']
    fat = [n for n in self.nutrients if n['id'] == 204][0]['amount_per_100g']
    carb = [n for n in self.nutrients if n['id'] == 205][0]['amount_per_100g']
    plt.pie([water, protein, fat, carb],
            labels=["water", "protein", "fat", "carb"],
            autopct='%1.1f%%')

  def __repr__(self):
    return f"{self.amount}g of {self.name}"


class Meal:
  def __init__(self, foods: List[Food]):
    self.foods = foods

  def compute_nutrients(self):
    combined_nutrients = []
    for food_ in self.foods:
      for nutrient_ in food_.nutrients:
        added = False
        for combined_nutrient in combined_nutrients:
          if combined_nutrient['id'] == nutrient_['id']:
            combined_nutrient['amount'] += nutrient_['amount']
            added = True
        if not added:
          combined_nutrients.append(copy.deepcopy(nutrient_))
    combined_nutrients = [{
        **n, 'amount': round(n['amount'], 2)
    } for n in combined_nutrients]
    return combined_nutrients

  def __repr__(self):
    return "\n".join([str(food) for food in self.foods])


def get_intake_profile(age: float,
                       sex: str,
                       is_lactating=False,
                       is_pregnant=False):
  def inner():
    assert sex in ["M", "F"]
    if is_lactating or is_pregnant:
      assert sex == "F"
    for entry in intake_profiles:
      min_years = entry['profile']['minAgeMonths'] / 12 + entry['profile'][
          'minAgeYears']
      max_years = entry['profile']['maxAgeMonths'] / 12 + (
          entry['profile']['maxAgeYears']
          if entry['profile']['maxAgeYears'] is not None else 100)
      if age >= min_years and age < max_years:
        if is_lactating and entry['profile']['lifeStageGroup'] == 'lactating':
          return entry
        if is_pregnant and entry['profile']['lifeStageGroup'] == 'pregnant':
          return entry
        if sex == "M" and entry['profile']['lifeStageGroup'] in [
            'infant', 'child', 'male'
        ]:
          return entry
        if sex == "F" and not is_lactating and not is_pregnant and entry[
            'profile']['lifeStageGroup'] in ['infant', 'child', 'female']:
          return entry

  entry = inner()
  if entry is not None:
    rdis = [{
        'value': value,
        'id': intake_profile_mapping[name]
    } for name, value in entry['RDI'].items()
            if name in intake_profile_mapping.keys()]
    uls = [{
        'value': value,
        'id': intake_profile_mapping[name]
    } for name, value in entry['UL'].items()
           if name in intake_profile_mapping.keys()]
    for global_ul in global_uls:
      matches = [ul for ul in uls if ul['id'] == global_ul['id']]
      if len(matches) == 0:
        uls.append(global_ul)
      elif matches[0]['value'] is None:
        match_i = [
            i for i, ul in enumerate(uls) if ul['id'] == global_ul['id']
        ][0]
        uls[match_i] = global_ul
    reversed_intake_profile_mapping
    target_amounts = []
    upper_limit_amounts = []
    for n_def in nutrient_definitions:
      rdi_counted = False
      ul_counted = False
      if n_def['id'] == 208:
        target_amounts.append(2000)
        upper_limit_amounts.append(3000)
      else:
        for rdi in rdis:
          if rdi['id'] == n_def['id']:
            if rdi['id'] == 255:
              target_amounts.append(rdi['value'] * 1000)
            elif rdi['id'] == 312:
              target_amounts.append(rdi['value'] / 1000)
            else:
              target_amounts.append(rdi['value'])
            rdi_counted = True
        for ul in uls:
          if ul['id'] == n_def['id']:
            if ul['id'] == 255:
              upper_limit_amounts.append(ul['value'] * 1000)
            elif ul['id'] == 312:
              upper_limit_amounts.append(ul['value'] / 1000)
            else:
              upper_limit_amounts.append(ul['value'])
            ul_counted = True
        if not rdi_counted:
          target_amounts.append(None)
        if not ul_counted:
          print(n_def['name'])
          upper_limit_amounts.append(None)
    return np.array(target_amounts), np.array(upper_limit_amounts)


def visualize_profile(target_amounts, upper_limit_amounts):
  lines = []
  for i, n_def in enumerate(nutrient_definitions):
    if not all([
        target_amounts[i] is None, upper_limit_amounts[i] is None, n_def['id']
        not in [204, 269]
    ]):
      lines.append({
          **n_def,
          "RDI":
          str(target_amounts[i]) +
          n_def['unitName'] if target_amounts[i] is not None else 'none',
          "UL":
          str(upper_limit_amounts[i]) +
          n_def['unitName'] if upper_limit_amounts[i] is not None else 'none',
      })
  pd.DataFrame(lines).to_csv("targets.csv")


def ratios_to_score(ratios):
  return np.where(ratios > 1, 1, ratios).sum(axis=-1)

def recommend(meal_nutrient_amounts,
              target_amounts,
              upper_limit_amounts,
              top_k=3,
              amount_to_recommend=100):
  target_amounts_placeholder = np.where(target_amounts == None, 0,
                                        target_amounts)
  upper_limits_placeholder = np.where(upper_limit_amounts == None, np.inf,
                                      upper_limit_amounts)
  ratios = np.where(
      meal_nutrient_amounts < target_amounts_placeholder,
      meal_nutrient_amounts / np.where(target_amounts_placeholder == 0, np.inf,
                                       target_amounts_placeholder),
      1 - (meal_nutrient_amounts - target_amounts_placeholder) /
      (upper_limits_placeholder - target_amounts_placeholder))
  candidate_nutrient_matrices = (
      meal_nutrient_amounts +
      (master_food_nutrient_amounts * amount_to_recommend / 100))
  ratios = np.where(
      candidate_nutrient_matrices < target_amounts_placeholder[np.newaxis],
      candidate_nutrient_matrices /
      np.where(target_amounts_placeholder == 0, np.inf,
               target_amounts_placeholder)[np.newaxis], 1 -
      (candidate_nutrient_matrices - target_amounts_placeholder[np.newaxis]) /
      (upper_limits_placeholder - target_amounts_placeholder)[np.newaxis])
  ratios = np.where(ratios < 0, 0, ratios)
  ratios = ratios**2
  food_scores = ratios.sum(axis=-1)
  top_foods = np.argsort(food_scores)[::-1][:top_k]
  return food_df.iloc[top_foods]


def search(query, vegetarian=False, num_results=16):
  embed = model(**tokenizer([query], return_tensors="pt",
                            padding=True)).pooler_output.detach().numpy()
  semantic_scores = np.matmul(search_index, embed.T)[:, 0] / (
      np.linalg.norm(search_index, axis=-1) * np.linalg.norm(embed))
  levenstein_scores = np.array([
      r[1] / 100 for r in list(
          thefuzz.process.extractWithoutOrder(query,
                                              food_df['shortened_name']))
  ]) * 0.5
  combined_scores = (semantic_scores + levenstein_scores) * (
      (food_df['popular_score'] + 10) / 20)
  top_results = np.argsort(combined_scores)[::-1]
  result_rows = food_df.iloc[top_results][:num_results * 2]
  result_rows['search_score'] = sorted(combined_scores)[::-1][:num_results * 2]
  if vegetarian:
    result_rows = result_rows[result_rows['is_vegetarian']]
  result_rows = result_rows.to_dict('records')[:num_results]
  result_rows = [r for r in result_rows if r['search_score'] > 0.4]
  return result_rows


if __name__ == "__main__":
  visualize_profile(*get_intake_profile(20, "M"))