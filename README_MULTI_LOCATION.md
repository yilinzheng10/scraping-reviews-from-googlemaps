# Complete Multi-Location Scraper Solution

## Overview

Your Google Maps review scraper now supports scraping **multiple locations** to collect reviews across different places. 

## What You Can Do Now

### Single Location (Original)
```bash
python app.py
```
Scrapes Dallas City Hall only. Output: `CityHall.xlsx` and `CityHall.json`

### Multiple Locations (New)
```bash
python scrape_multiple_locations.py
```
Scrapes all locations in `locations.json`. Output: Organized by location in separate folders + summary report.

## Getting Started with Multiple Locations

### Step 1: Pre-configured Setup
The system comes with downtown Dallas public space locations already configured

Just run:
```bash
python scrape_multiple_locations.py
```

Expected output: **60-110 reviews** across 6 locations (15-20 min runtime)

### Step 2: Add Your Own Locations

#### Method A: Manual Edit (Recommended for beginners)
1. Open `locations.json` in a text editor
2. Add new location entries:
```json
{
  "name": "Your Park Name",
  "url": "https://www.google.com/maps/place/Your+Park/@32.7764,-96.7996,...",
  "output_name": "YourParkName"
}
```
3. Save and run

#### Method B: Interactive Tool
```bash
python find_urls.py
```
Menu-driven tool to:
- Add new locations interactively
- View existing locations
- Validate Google Maps URLs

#### Method C: Command Line
```bash
python find_urls.py "Park Name" "https://www.google.com/maps/place/..."
```

## Finding Google Maps URLs

### Easiest Way:
1. Go to https://www.google.com/maps
2. Search for a place (e.g., "parks in downtown Dallas")
3. Click on the place name in the results
4. Copy the URL from your browser's address bar
5. Paste into `locations.json`

### URL Format Examples:
```
https://www.google.com/maps/place/Klyde+Warren+Park/@32.7913,-96.8021,15z/data=!3m2!1e3!5s0x86e82a1b...
https://www.google.com/maps/place/Pioneer+Plaza/@32.7767,-96.8032,15z/data=!3m2!1e3!5s0x86e842e8...
```

## Output Structure

After scraping multiple locations:

```
ScrapingOutput/
└── locations/                    ← All multi-location results here
    ├── CityHall/
    │   ├── CityHall.xlsx        ← Review data for this location
    │   └── CityHall.json        ← Same data as JSON
    ├── KlydeWarrenPark/
    │   ├── KlydeWarrenPark.xlsx
    │   └── KlydeWarrenPark.json
    ├── PioneerPlaza/
    │   ├── PioneerPlaza.xlsx
    │   └── PioneerPlaza.json
    ├── [other locations...]
    └── SUMMARY.xlsx             ← Master report with all locations
```

**Single location output still goes to the main directory:**
```
ScrapingOutput/
├── CityHall.xlsx               ← From running app.py
└── CityHall.json
```

## Data Formats

### Excel File (per location)
Columns:
- **name** - Reviewer name
- **rating** - Star rating (1-5)
- **date** - Posted date ("a week ago", "2 months ago", etc.)
- **comment** - Full review text
- **latitude** - Location latitude coordinate
- **longitude** - Location longitude coordinate

### JSON Files (per location)
```json
{
  "location": "Park Name",
  "scraped_at": "2025-12-01T15:30:45.123456",
  "coordinates": {
    "latitude": 32.7913,
    "longitude": -96.8021
  },
  "total_reviews": 15,
  "reviews": [
    {
      "name": "Reviewer Name",
      "rating": "5",
      "date": "a week ago",
      "comment": "Great place to visit..."
    },
    ...
  ]
}
```

**Runtime varies based on:**
- Number of reviews per location
- Google Maps load times
- Your internet speed
- System performance


## Troubleshooting

**"Could not open reviews panel"**
- Make sure the URL points directly to the place (search result)
- Try opening the URL manually to verify it's correct

**Missing reviews in output**
- Google sometimes rate-limits after many scrolls
- Try running the same location again later
- Some places may have fewer reviews available

**URLs expire or change**
- Google Maps URLs can change format
- Always copy fresh URLs from your browser

| Problem | Solution |
|---------|----------|
| "Could not open reviews panel" | Verify URL directly in browser first |
| Missing reviews | Some locations have fewer reviews; try adding more locations |
| Script is slow | That's normal; Google throttles repeated requests |
| URL format error | Use fresh URL from browser address bar |
| Excel file locked | Close the file if open in Excel before running |

## Tips for Best Results

1. **Test with 1-2 locations first** - Make sure everything works
2. **Run during off-peak hours** - Google is more permissive when not busy
3. **Add popular locations** - Parks/museums/public places have more reviews
4. **Mix location types** - Different types often have different review counts
5. **Don't run too frequently** - Wait 1-2 hours between batch runs

## Command Reference

```bash
# Scrape all locations in config
python scrape_multiple_locations.py

# Open URL helper
python find_urls.py

# Scrape single location (original)
python app.py

# Check Python syntax
python -m py_compile scrape_multiple_locations.py
```

## File Reference

| File | Purpose | Edit? |
|------|---------|-------|
| `scrape_multiple_locations.py` | Main batch scraper | No (unless customizing) |
| `locations.json` | Location configuration | **Yes - add your locations here** |
| `find_urls.py` | Helper to manage locations | No |
| `app.py` | Original single-location scraper | No |
| `env.py` | Configuration (existing) | Optional |
| `MULTI_LOCATION_GUIDE.md` | Full documentation | No |

## Next Steps

1. **Run the default configuration:**
   ```bash
   python scrape_multiple_locations.py
   ```

2. **Check the results:**
   - Open `ScrapingOutput/locations/...`
   - View individual location folders

3. **Add more locations**
   - Edit `locations.json`
   - Add more Google Maps URLs
   - Re-run the script

4. **Merge data**
   - Combine data from multiple runs
   - Create master dataset

5. **Run Sentiment Analysis**


Good luck scraping! 