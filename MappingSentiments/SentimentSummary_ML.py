import pandas as pd
import json
from transformers import pipeline
from keybert import KeyBERT

# Load data
df = pd.read_excel("DallasDesignSprint/ScrapingOutput/all_reviews_combined.xlsx")

# HuggingFace pipelines
# https://huggingface.co/cardiffnlp/twitter-roberta-base-sentiment
summarizer = pipeline("summarization", model="facebook/bart-large-cnn")

sentiment_analyzer = pipeline("sentiment-analysis",
                              model="cardiffnlp/twitter-roberta-base-sentiment")

# KeyBERT model for keyword extraction
kw_model = KeyBERT("all-mpnet-base-v2")

# convert comments to strings
df["comment"] = df["comment"].fillna("").astype(str)


#  Sentiment classifier
def classify_sentiment(text):
    if not isinstance(text, str) or text.strip() == "":
        return "neutral"

    cleaned = text[:512]
    result = sentiment_analyzer(cleaned)[0]["label"]

    if result == "LABEL_2":
        return "positive"
    elif result == "LABEL_0":
        return "negative"
    return "neutral"

#  Keyword extractor (unsupervised)
def extract_keywords(text):
    if not isinstance(text, str) or text.strip() == "":
        return []

    try:
        keywords = kw_model.extract_keywords(
            text,
            keyphrase_ngram_range=(1, 2),
            stop_words="english",
            use_maxsum=True,
            nr_candidates=10,
            top_n=5
        )
        # extract just the keyword text
        return [kw for kw, score in keywords]

    except:
        return []



#  Classify each keyword by sentiment
def classify_keywords(keyword_list):
    pos_kw, neg_kw = [], []
    for kw in keyword_list:
        sent = classify_sentiment(kw)
        if sent == "positive":
            pos_kw.append(kw)
        elif sent == "negative":
            neg_kw.append(kw)
    return pos_kw, neg_kw


# Compute sentiment + keywords per review
df["sentiment"] = df["comment"].apply(classify_sentiment)
df["keywords"] = df["comment"].apply(extract_keywords)

df["pos_kw"] = df["keywords"].apply(lambda kws: classify_keywords(kws)[0])
df["neg_kw"] = df["keywords"].apply(lambda kws: classify_keywords(kws)[1])


#  Group by location
grouped = df.groupby("source_location")
features = []

for location, group in grouped:
    comments = " ".join(str(c) for c in group["comment"])

    lat = float(group["latitude"].mean())
    lon = float(group["longitude"].mean())

    # Sentiment counts
    pos_count = (group["sentiment"] == "positive").sum()
    neg_count = (group["sentiment"] == "negative").sum()
    neu_count = (group["sentiment"] == "neutral").sum()

    # Summary
    #Combine all comments into a single string
    all_comments = " ".join(str(c) for c in group["comment"])

    # Split text into chunks (10,000 char) respect the max token limit of the summarizer model (BART-Large-CNN limit is 1024 tokens ~3,000-4,000 characters). Using 10k is safer for combining multiple reviews.
    CHUNK_SIZE = 3500 
    comment_chunks = [all_comments[i:i + CHUNK_SIZE] for i in range(0, len(all_comments), CHUNK_SIZE)]

    initial_summaries = []

    #Summarize each chunk (First-Level Summarization)
    SHORT_TEXT_THRESHOLD = 1000 

    for chunk in comment_chunks:
        chunk_len = len(chunk)
        
        if not chunk.strip():
            continue # Skip empty chunks

        if chunk_len < SHORT_TEXT_THRESHOLD:
            # If the chunk is very short, append the text directly
            initial_summaries.append(chunk.strip())
            continue
            
        # Dynamically set max_length: min(Global Cap: 150, 1/3 of input length)
        dynamic_max_length = min(150, chunk_len // 3) 
        
        # Ensure min_length is not greater than max_length
        safe_min_length = max(10, min(20, dynamic_max_length - 5))
        
        try:
            chunk_summary = summarizer(
                chunk, 
                max_length=dynamic_max_length,
                min_length=safe_min_length,
                do_sample=False
            )[0]["summary_text"]
            initial_summaries.append(chunk_summary)
        
        except Exception: 
            # Catch all exceptions (IndexError, Tokenizer error) and skip the chunk
            # This is the safest way to ensure the script doesn't crash or halt
            continue
                
    #Combine all initial summaries
    combined_summaries = " ".join(initial_summaries)

    #Create a final summary of the combined summaries (Second-Level Summarization)
    if combined_summaries:
        FINAL_TEXT_THRESHOLD = 500
        
        if len(combined_summaries) < FINAL_TEXT_THRESHOLD:
            # If the combined text is short (e.g., only a few very short reviews), 
            # use the text itself as the final summary to avoid errors/warnings.
            summary = combined_summaries
            
        else:
            # Final summarization
            final_max_length = min(120, len(combined_summaries) // 3)
            safe_final_min_length = max(10, min(20, final_max_length - 5))

            try:
                summary = summarizer(
                    combined_summaries, 
                    max_length=final_max_length, 
                    min_length=safe_final_min_length, 
                    do_sample=False
                )[0]["summary_text"]
            except Exception:
                # If the final summarization fails (rare), fall back to the raw combined text
                summary = combined_summaries
    else:
        summary = "No meaningful summary could be generated."
    # --- SUMMARY LOGIC END ---

    # Overall sentiment
    if pos_count >= neg_count and pos_count >= neu_count:
        overall = "positive"
    elif neg_count > pos_count and neg_count >= neu_count:
        overall = "negative"
    else:
        overall = "neutral"

    # Aggregate keywords for the entire location
    all_pos_kw = sorted(list(set(sum(group["pos_kw"], []))))
    all_neg_kw = sorted(list(set(sum(group["neg_kw"], []))))

    # Build GeoJSON feature
    features.append({
        "type": "Feature",
        "properties": {
            "location": location,
            "summary": summary,
            "overall_sentiment": overall,
            "positive": int(pos_count),
            "negative": int(neg_count),
            "neutral": int(neu_count),
            "positive_keywords": all_pos_kw,
            "negative_keywords": all_neg_kw
        },
        "geometry": {
            "type": "Point",
            "coordinates": [lon, lat]
        }
    })

geojson = {"type": "FeatureCollection", "features": features}

with open("MappingSentiments/dallas_reviews.geojson", "w") as f:
    json.dump(geojson, f, indent=2)

print("Saved → dallas_reviews.geojson")