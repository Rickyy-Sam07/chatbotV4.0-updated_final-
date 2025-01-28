# -*- coding: utf-8 -*-
"""Final_chatbot_api.ipynb

Automatically generated by Colab.

Original file is located at
    https://colab.research.google.com/drive/14Mt8RUY_Q-8mE_Zi8n6UkBPPedmgwjOI
"""
'''
pip install transformers dataset accelerate

pip install groq

pip install pyngrok
pip install transformers dataset accelerate groq fastapi uvicorn pyngrok nest_asyncio
'''

'''
import requests

url = "https://7ec2-34-125-187-222.ngrok-free.app/chatbot"
payload = {"message": "Hello"}
headers = {"Content-Type": "application/json"}

response = requests.post(url, json=payload, headers=headers)
print(response.json())
'''

# Install required libraries


import numpy as np
import pandas as pd
import zipfile
import os
import json
import random
from pyngrok import ngrok
import nest_asyncio
import tensorflow as tf
from tensorflow.keras.layers import Input, Embedding, LSTM, Dense
from tensorflow.keras.models import Model, load_model
from tensorflow.keras.preprocessing.text import Tokenizer
from tensorflow.keras.preprocessing.sequence import pad_sequences
from sklearn.preprocessing import LabelEncoder
from groq import Groq
from fastapi import FastAPI
from pydantic import BaseModel
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5500"],  # Replace '*' with specific frontend URL for better security
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Extract dataset
zip_file_path = 'archive.zip'
with zipfile.ZipFile(zip_file_path, 'r') as zip_ref:
    zip_ref.extractall('extracted')

# Check dataset files
for dirname, _, filenames in os.walk('extracted'):
    for filename in filenames:
        print(os.path.join(dirname, filename))

# Load and preprocess intents dataset
with open('extracted/intents.json') as file:
    data = json.load(file)

texts = []
intents = []
for intent in data['intents']:
    for text in intent['text']:
        texts.append(text)
        intents.append(intent['intent'])

# Tokenize texts
tokenizer = Tokenizer()
tokenizer.fit_on_texts(texts)
encoded_texts = tokenizer.texts_to_sequences(texts)
max_len = max([len(x) for x in encoded_texts])
padded_texts = pad_sequences(encoded_texts, maxlen=max_len, padding='post')

# Encode intents
le = LabelEncoder()
encoded_intents = le.fit_transform(intents)
num_intents = len(le.classes_)
encoded_intents = tf.one_hot(encoded_intents, depth=num_intents)

# Build and train the model
input_layer = Input(shape=(max_len,))
embedding_layer = Embedding(input_dim=len(tokenizer.word_index) + 1, output_dim=128, input_length=max_len)(input_layer)
lstm_layer = LSTM(128)(embedding_layer)
output_layer = Dense(num_intents, activation='softmax')(lstm_layer)
model = Model(inputs=input_layer, outputs=output_layer)

model.compile(loss='categorical_crossentropy', optimizer='adam', metrics=['accuracy'])
model.fit(padded_texts, encoded_intents, epochs=50, batch_size=16)

# Save the model
model.save('chatbot_model34.keras')


# Initialize FastAPI app
app = FastAPI()

# Request model for FastAPI
class ChatRequest(BaseModel):
    message: str

# Load tokenizer and model
tokenizer = Tokenizer()
tokenizer.fit_on_texts(texts)
model = load_model('chatbot_model34.keras')
max_len = model.input_shape[1]
le = LabelEncoder()
le.fit(intents)

# Groq API key setup
os.environ["GROQ_API_KEY"] = ""

# Define chatbot response functions
def groq_response(user_input):
    """Fetch a response from Groq."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        return "Error: GROQ_API_KEY is not set in the environment."

    client = Groq(api_key=api_key)
    system_prompt = {
        "role": "assistant",
        "content": "You are a helpful assistant. The college name is IEM Kolkata. Provide relevant answers."
    }

    chat_history = [system_prompt, {"role": "user", "content": user_input}]
    response = client.chat.completions.create(
        model="llama3-70b-8192",
        messages=chat_history,
        max_tokens=250,
        temperature=1.2
    )
    return response.choices[0].message.content

def predict_intent(user_input):
    """Predict the user's intent."""
    encoded_input = tokenizer.texts_to_sequences([user_input])
    padded_input = pad_sequences(encoded_input, maxlen=max_len, padding='post')
    predictions = model.predict(padded_input)[0]
    intent_idx = np.argmax(predictions)
    confidence = predictions[intent_idx]
    intent_label = le.inverse_transform([intent_idx])[0]
    return intent_label, confidence


from pymongo import MongoClient
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# MongoDB setup
MONGO_URI = "mongodb://localhost:27017"  # Replace with your MongoDB URI
client = MongoClient(MONGO_URI)
db = client['chatbot']
prompts_collection = db['prompts']
admin_collection = db['admins']

# Insert example admin credentials
admin_collection.insert_one({
    "username": "admin",
    "password": "password"  # Plaintext password (not recommended for production)
})

# FastAPI app
app = FastAPI()

# Request model for saving prompts
class ChatRequest(BaseModel):
    message: str

# Admin credentials model
class AdminCredentials(BaseModel):
    username: str
    password: str

# Track admin login status in-memory (this is a simple solution, not for production)
admin_sessions = {}

@app.post("/chatbot")
def chatbot(request: ChatRequest):
    user_input = request.message.strip()

    # Check if user wants to enter admin mode
    if user_input == "./dev":
        return {"response": "Enter admin username and password as 'username,password'."}

    # Handle admin login
    if "," in user_input:
        username, password = user_input.split(",", 1)
        admin = admin_collection.find_one({"username": username, "password": password})
        if admin:
            admin_sessions[username] = True  # Mark admin as logged in
            return {"response": "Login successful. ."}
        else:
            return {"response": "Invalid admin credentials. Try again."}

    # Check if logged in as admin and fetch prompts
    if user_input.lower() == "view prompts":
        for username in admin_sessions:
            if admin_sessions.get(username, False):
                prompts = list(prompts_collection.find({}, {"_id": 0, "prompt": 1}))
                return {"response": prompts}
        return {"response": "You must log in as an admin ."}

    # Regular chatbot handling
    CONFIDENCE_THRESHOLD = 0.99555
    prompts_collection.insert_one({"prompt": user_input})
    intent_label, confidence = predict_intent(user_input)

    if confidence < CONFIDENCE_THRESHOLD:
        try:
            response = groq_response(user_input)
        except Exception:
            response = "I'm sorry, I couldn't process your question."
    else:
        response = next(
            (random.choice(intent['responses']) for intent in data['intents'] if intent['intent'] == intent_label),
            "I'm sorry, I don't have an answer for that."
        )
    return {"response": response}


@app.post("/admin/login")
def admin_login(credentials: AdminCredentials):
    admin = admin_collection.find_one({"username": credentials.username, "password": credentials.password})
    if not admin:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return {"message": "Login successful"}

@app.get("/admin/prompts")
def get_prompts(username: str, password: str):
    # Verify admin credentials
    admin = admin_collection.find_one({"username": username, "password": password})
    if not admin:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Fetch all saved prompts
    prompts = list(prompts_collection.find({}, {"_id": 0, "prompt": 1}))

    # Return prompts
    return {"prompts": prompts}



# Expose FastAPI with ngrok
ngrok.set_auth_token("2qfmcYifn6s6LPsgpSyj4GH1eM1_2F3NQNuZ7KUqjsEjHTwH")  # Replace with your ngrok auth token
public_url = ngrok.connect(8000)
print(f"Public URL: {public_url}")

# Run the app
nest_asyncio.apply()
uvicorn.run(app, host="0.0.0.0", port=8000)