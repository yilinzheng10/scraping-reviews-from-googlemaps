import pandas as pd
import json
from transformers import pipeline
from keybert import KeyBERT

# Load data
df = pd.read_excel("DallasDesignSprint/ScrapingOutput/all_reviews_combined.xlsx")

# HuggingFace pipelines
summarizer = pipeline("summarization", model="facebook/bart-large-cnn")

sentiment_analyzer = pipeline("sentiment-analysis",
                              model="cardiffnlp/twitter-roberta-base-sentiment")

# KeyBERT model for keyword extraction
kw_model = KeyBERT("all-mpnet-base-v2")

# Ensure comments are strings
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
    comments_trim = comments[:600]
    summary = summarizer(comments_trim, max_length=120, min_length=1, do_sample=False)[0]["summary_text"]

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