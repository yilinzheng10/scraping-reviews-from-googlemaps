"""
Merge all per-location scraped review files into one master dataset.
Saves `all_reviews_combined.xlsx` and `all_reviews_combined.json` in the ScrapingOutput folder.
"""
import os
import glob
import json
import re
import difflib
import argparse
import pandas as pd

BASE_OUT = os.path.join(os.path.dirname(__file__), 'DallasDesignSprint', 'ScrapingOutput')
LOCATIONS_DIR = os.path.join(BASE_OUT, 'locations')


def read_location_files():
    """Read per-location files (Excel or JSON) and return a DataFrame with source metadata."""
    rows = []
    files_found = 0

    if not os.path.isdir(LOCATIONS_DIR):
        print('No locations output folder found at', LOCATIONS_DIR)
        return pd.DataFrame()

    for loc_folder in sorted(os.listdir(LOCATIONS_DIR)):
        loc_path = os.path.join(LOCATIONS_DIR, loc_folder)
        if not os.path.isdir(loc_path):
            continue

        excel_files = glob.glob(os.path.join(loc_path, '*.xlsx'))
        json_files = glob.glob(os.path.join(loc_path, '*.json'))

        data_df = None
        payload = None
        source_name = loc_folder

        if excel_files:
            try:
                data_df = pd.read_excel(excel_files[0])
                files_found += 1
                source_file = excel_files[0]
            except Exception as e:
                print('Error reading', excel_files[0], e)
                data_df = None

        if data_df is None and json_files:
            try:
                with open(json_files[0], 'r', encoding='utf-8') as jf:
                    payload = json.load(jf)
                reviews = payload.get('reviews') if isinstance(payload, dict) and 'reviews' in payload else payload
                data_df = pd.DataFrame(reviews)
                files_found += 1
                source_file = json_files[0]
            except Exception as e:
                print('Error reading', json_files[0], e)
                data_df = None

        if data_df is None:
            print('No data file found in', loc_path)
            continue

        # Map likely column names to canonical columns
        cols = {c.lower(): c for c in data_df.columns}

        def get_col(df, names, default=''):
            for n in names:
                if n in cols:
                    return df[cols[n]]
            return pd.Series([default] * len(df))

        df = pd.DataFrame()
        df['name'] = get_col(data_df, ['name', 'reviewer', 'author'])
        df['comment'] = get_col(data_df, ['comment', 'review', 'text'])
        df['rating'] = get_col(data_df, ['rating', 'stars'])
        df['date'] = get_col(data_df, ['date', 'time'])
        df['latitude'] = get_col(data_df, ['latitude', 'lat'])
        df['longitude'] = get_col(data_df, ['longitude', 'lon', 'lng', 'lng'])

        df['source_location'] = source_name
        df['source_file'] = os.path.basename(source_file)

        # If JSON payload includes an explicit location name, prefer it
        if isinstance(payload, dict) and payload.get('location'):
            df['source_name'] = payload.get('location')
        else:
            df['source_name'] = source_name

        rows.append(df)

    print(f'Found {files_found} location files to merge.')
    if rows:
        merged = pd.concat(rows, ignore_index=True, sort=False)
    else:
        merged = pd.DataFrame(columns=['name', 'comment', 'rating', 'date', 'latitude', 'longitude', 'source_location', 'source_name', 'source_file'])

    return merged


def normalize_text(s):
    if s is None:
        return ''
    s = str(s)
    s = s.lower()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"[^0-9a-z\s]", "", s)
    s = s.strip()
    return s


def rating_to_float(x):
    try:
        return float(x)
    except Exception:
        try:
            return float(str(x).split()[0])
        except Exception:
            return None


def dedupe_across_locations(df, similarity_threshold=0.85):
    """Group similar/duplicate reviews across locations using normalized comment text and fuzzy matching.

    Returns a grouped DataFrame with one row per group and columns summarizing merged locations and ratings.
    """
    # Prepare normalized comment and other fields
    df = df.copy()
    df['name'] = df['name'].fillna('').astype(str).str.strip()
    df['comment'] = df['comment'].fillna('').astype(str)
    df['norm_comment'] = df['comment'].apply(normalize_text)
    df['rating_f'] = df['rating'].apply(rating_to_float)

    groups = []  # list of dicts representing group aggregates
    reps = []  # representative normalized comments for groups

    for idx, row in df.iterrows():
        nc = row['norm_comment']
        placed = False
        # Try to find an existing group with a close-enough representative
        for gi, rep in enumerate(reps):
            if not rep:
                continue
            score = difflib.SequenceMatcher(None, rep, nc).ratio()
            if score >= similarity_threshold:
                groups[gi]['rows'].append(row.to_dict())
                # update rep to be the longest (more stable) comment
                if len(nc) > len(rep):
                    reps[gi] = nc
                placed = True
                break

        if not placed:
            reps.append(nc)
            groups.append({'rep': nc, 'rows': [row.to_dict()]})

    # Build summary rows
    out_rows = []
    for gid, g in enumerate(groups, start=1):
        rows = g['rows']
        comments = [r.get('comment', '') for r in rows]
        names = [r.get('name', '') for r in rows]
        ratings = [r.get('rating_f') for r in rows if r.get('rating_f') is not None]
        locations = sorted(list({r.get('source_location') for r in rows if r.get('source_location')}))

        out = {
            'group_id': gid,
            'representative_comment': max(comments, key=lambda x: len(x)) if comments else '',
            'sample_name': names[0] if names else '',
            'occurrences': len(rows),
            'locations_merged': locations,
            'avg_rating': (sum(ratings) / len(ratings)) if ratings else None,
            'ratings_list': ratings,
            'raw_rows': rows,
        }
        out_rows.append(out)

    grouped_df = pd.DataFrame(out_rows)
    return grouped_df


def save_outputs_raw(out_df_raw):
    """Save only the combined raw rows to Excel and JSON."""
    os.makedirs(BASE_OUT, exist_ok=True)
    out_xlsx = os.path.join(BASE_OUT, 'all_reviews_combined.xlsx')
    out_json = os.path.join(BASE_OUT, 'all_reviews_combined.json')

    # Drop internal helper columns
    df_clean = out_df_raw.drop(columns=['source_name', 'norm_comment', 'name_norm'], errors='ignore')

    try:
        df_clean.to_excel(out_xlsx, index=False)
        print('Saved combined Excel to', out_xlsx)
    except Exception as e:
        print('Failed to write Excel:', e)

    try:
        with open(out_json, 'w', encoding='utf-8') as jf:
            json.dump(df_clean.to_dict(orient='records'), jf, ensure_ascii=False, indent=2)
        print('Saved combined JSON to', out_json)
    except Exception as e:
        print('Failed to write JSON:', e)


def save_grouped_outputs(grouped_df, out_df_raw):
    """Save grouped summary and raw combined rows (used only when grouping requested)."""
    os.makedirs(BASE_OUT, exist_ok=True)
    out_groups_xlsx = os.path.join(BASE_OUT, 'all_reviews_groups.xlsx')
    out_groups_json = os.path.join(BASE_OUT, 'all_reviews_groups.json')

    try:
        grouped_df_copy = grouped_df.copy()
        grouped_df_copy = grouped_df_copy.drop(columns=['raw_rows'], errors='ignore')
        grouped_df_copy.to_excel(out_groups_xlsx, index=False)
        print('Saved grouped Excel to', out_groups_xlsx)
    except Exception as e:
        print('Failed to write grouped Excel:', e)

    try:
        with open(out_groups_json, 'w', encoding='utf-8') as jf:
            json.dump(grouped_df.to_dict(orient='records'), jf, ensure_ascii=False, indent=2)
        print('Saved grouped JSON to', out_groups_json)
    except Exception as e:
        print('Failed to write grouped JSON:', e)


def print_summary(grouped_df, out_df_raw):
    total_reviews = len(out_df_raw)
    unique_groups = len(grouped_df)
    ratings = out_df_raw['rating'].apply(rating_to_float).dropna()
    avg_rating = ratings.mean() if not ratings.empty else None

    print('\n--- Merge Summary ---')
    print('Total raw reviews found:', total_reviews)
    print('Unique review groups after dedupe:', unique_groups)
    print('Avg rating (where available):', round(avg_rating, 3) if avg_rating is not None else 'N/A')


def main():
    parser = argparse.ArgumentParser(description='Merge per-location review outputs.')
    parser.add_argument('--group', action='store_true', help='Also perform fuzzy grouping of similar reviews')
    parser.add_argument('--threshold', type=float, default=0.85, help='Similarity threshold for grouping (0-1)')
    args = parser.parse_args()

    merged = read_location_files()
    if merged is None or merged.empty:
        print('No data to merge.')
        return

    # Basic exact dedupe by normalized comment + name + date to remove obvious duplicates
    merged['norm_comment'] = merged['comment'].apply(normalize_text)
    merged['name_norm'] = merged['name'].fillna('').astype(str).str.strip().str.lower()
    before = len(merged)
    merged = merged.drop_duplicates(subset=['name_norm', 'norm_comment', 'date'], keep='first').reset_index(drop=True)
    after = len(merged)
    print(f'Removed exact duplicates: {before} -> {after}')

    # Save the combined-only outputs
    save_outputs_raw(merged)
    print('\nCombined rows:', len(merged))

    # If grouping requested, run grouping and save grouped outputs
    if args.group:
        grouped = dedupe_across_locations(merged, similarity_threshold=args.threshold)
        save_grouped_outputs(grouped, merged)
        print_summary(grouped, merged)


if __name__ == '__main__':
    main()
