import os
import pickle

# Get the directory of the current script to avoid path issues
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

df_path = os.path.join(BASE_DIR, 'df.pkl')
indices_path = os.path.join(BASE_DIR, 'indices.pkl')

# Open with 'rb' (Read Binary) mode
with open(df_path, 'rb') as f:
    df = pickle.load(f)

with open(indices_path, 'rb') as f:
    indices = pickle.load(f)