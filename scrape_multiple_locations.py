"""
Multi-location Google Maps review scraper.
Loads locations from locations.json and scrapes reviews for each location.
"""

import json
import os
import time
import re
from datetime import datetime
import pandas as pd
from bs4 import BeautifulSoup

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from env import DriverLocation

def create_driver():
    """Create and return a Chrome WebDriver instance."""
    options = webdriver.ChromeOptions()
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_argument('lang=en-US')
    options.add_experimental_option('prefs', {
        'profile.managed_default_content_settings.notifications': 2,
        'credentials_enable_service': False,
        'profile.password_manager_enabled': False,
    })
    driver = webdriver.Chrome(options=options)
    return driver


def scrape_location(location_config):
    """Scrape reviews for a single location.
    
    Args:
        location_config: dict with 'name', 'url', 'output_name' keys
    
    Returns:
        tuple: (location_name, reviews_list, coordinates)
    """
    location_name = location_config['name']
    url = location_config['url']
    output_name = location_config['output_name']
    
    print(f"\n{'='*60}")
    print(f"Scraping: {location_name}")
    print(f"URL: {url}")
    print(f"{'='*60}")
    
    driver = None
    try:
        driver = create_driver()
        
        # Navigate to location
        print('Loading page...')
        driver.get(url)
        time.sleep(3)
        
        # Handle GDPR consent if present
        if 'consent.google.com' in driver.current_url:
            try:
                driver.execute_script('document.getElementsByTagName("form")[0].submit()')
                time.sleep(2)
            except:
                pass
        
        # Open reviews panel
        print('Opening reviews panel...')
        opened = False
        try:
            btn = driver.find_element(By.XPATH, "//button[contains(., 'More reviews')]")
            btn.click()
            time.sleep(2)
            opened = True
        except:
            try:
                el = driver.find_element(By.XPATH, "//*[contains(text(), 'More reviews')]")
                el.click()
                time.sleep(2)
                opened = True
            except:
                pass
        
        if not opened:
            print(f'Warning: Could not open reviews panel for {location_name}')
        
        # Scroll to load more reviews
        print('Scrolling to load reviews...')
        scroll_iterations = 30
        for i in range(scroll_iterations):
            # Strategy 1: Scroll window
            try:
                driver.execute_script('window.scrollTo(0, document.body.scrollHeight)')
                time.sleep(0.15)
            except:
                pass
            
            # Strategy 2: Find and scroll modal
            try:
                modal_selectors = [
                    "div[role='dialog'] div[tabindex='-1']",
                    "div[role='dialog']",
                    "div[aria-modal='true']",
                ]
                for sel in modal_selectors:
                    els = driver.find_elements(By.CSS_SELECTOR, sel)
                    for el in els:
                        try:
                            if el.is_displayed():
                                driver.execute_script('arguments[0].scrollTop = arguments[0].scrollHeight', el)
                                time.sleep(0.1)
                        except:
                            pass
            except:
                pass
            
            # Strategy 3: Expand "More" buttons
            try:
                more_btns = driver.find_elements(By.XPATH, "//button[contains(text(), 'More')]")
                for btn in more_btns[:5]:
                    try:
                        driver.execute_script('arguments[0].scrollIntoView(true);', btn)
                        time.sleep(0.05)
                        driver.execute_script('arguments[0].click();', btn)
                        time.sleep(0.1)
                    except:
                        pass
            except:
                pass
            
            if (i + 1) % 10 == 0:
                print(f'  Scroll iteration {i+1}/{scroll_iterations}')
            
            if i % 5 == 4:
                time.sleep(0.5)
        
        # Extract reviews from page
        print('Extracting reviews...')
        page_html = driver.page_source
        soup = BeautifulSoup(page_html, 'html.parser')
        
        reviews_data = []
        seen = set()
        
        reviews_by_id = soup.select('div[data-review-id]')
        print(f'  Found {len(reviews_by_id)} review containers')
        
        for review_container in reviews_by_id:
            try:
                # Extract name
                name = 'Anonymous'
                name_el = review_container.select_one('div.d4r55')
                if name_el:
                    name = name_el.get_text(strip=True)
                
                # Extract rating
                rating = '-'
                for el in review_container.find_all(attrs={'aria-label': re.compile(r'star', re.I)}):
                    al = el.get('aria-label', '')
                    m = re.search(r'(\d+(?:\.\d+)?)\s*star', al, re.I)
                    if m:
                        rating = m.group(1)
                        break
                
                # Extract date and comment
                all_text = review_container.get_text()
                
                # Find date
                date = ''
                date_match = re.search(r'(a\s+)?(\d+)?\s*(hour|day|week|month|year)s?\s+ago', all_text, re.I)
                if date_match:
                    date = date_match.group(0).strip()
                else:
                    today_match = re.search(r'\b(today|yesterday)\b', all_text, re.I)
                    if today_match:
                        date = today_match.group(0).strip()
                
                # Extract comment
                comment = ''
                if date:
                    date_pos = all_text.find(date)
                    if date_pos != -1:
                        after_date = all_text[date_pos + len(date):]
                        after_new = re.sub(r'^\s*New\s*', '', after_date, flags=re.I)
                        comment = re.sub(r'(Like|Share|(?:0:\d{2})+).*$', '', after_new, flags=re.I).strip()
                        comment = re.sub(r'[\ue000-\uf8ff]', '', comment).strip()
                
                # Dedupe
                key = (name, comment, date)
                if key not in seen:
                    seen.add(key)
                    reviews_data.append({
                        'name': name,
                        'comment': comment,
                        'rating': rating,
                        'date': date
                    })
            
            except Exception:
                continue
        
        # Extract coordinates using the !3d and !4d markers for the Place of Interest
        current_url = driver.current_url
        lat = None
        lon = None
        
        try:
            # New regex pattern to match coordinates associated with the Place of Interest (!3d<lat>!4d<lon>)
            # This is much more reliable than the map view coordinates (@<lat>,<lon>)
            m = re.search(r"!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)", current_url)
            
            if m:
                # Group 1 is Latitude, Group 2 is Longitude
                lat = float(m.group(1))
                lon = float(m.group(2))
                print(f'  Coordinates found via PoI URL markers: {lat}, {lon}')
            else:
                # Fallback to map view coordinates (less accurate)
                m_fallback = re.search(r"@(-?\d+\.\d+),(-?\d+\.\d+)", current_url)
                if m_fallback:
                    lat = float(m_fallback.group(1))
                    lon = float(m_fallback.group(2))
                    print(f'  Warning: Coordinates found via map view fallback: {lat}, {lon}')
                else:
                    print('  Coordinates could not be reliably extracted from URL.')
            
        except Exception as e:
            print(f'  Coordinate extraction error: {e}')
            pass
        
        print(f'✓ Extracted {len(reviews_data)} unique reviews for {location_name}')
        return location_name, reviews_data, {'latitude': lat, 'longitude': lon}, output_name
    
    #raise exceptions to be caught in main flow
    except Exception as e:
        print(f'✗ Error scraping {location_name}: {e}')
        return location_name, [], {}, output_name
    # ensure driver is closed
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass

# Save individual location output
def save_location_output(location_name, reviews, coordinates, output_name):
    """Save reviews to Excel and JSON files organized by location."""
    
    # Create location-specific output directory
    output_dir = os.path.join(DriverLocation, 'locations', output_name)
    os.makedirs(output_dir, exist_ok=True)
    
    # Save to Excel
    if reviews:
        df = pd.DataFrame(reviews)
        df['latitude'] = coordinates.get('latitude', '')
        df['longitude'] = coordinates.get('longitude', '')
        
        excel_path = os.path.join(output_dir, f'{output_name}.xlsx')
        try:
            df.to_excel(excel_path, index=False)
            print(f'  Excel: {excel_path}')
        except Exception as e:
            print(f'  Excel error: {e}')
    
    # Save to JSON
    json_payload = {
        'location': location_name,
        'scraped_at': datetime.now().isoformat(),
        'coordinates': coordinates,
        'total_reviews': len(reviews),
        'reviews': reviews
    }
    
    json_path = os.path.join(output_dir, f'{output_name}.json')
    try:
        with open(json_path, 'w', encoding='utf-8') as jf:
            json.dump(json_payload, jf, ensure_ascii=False, indent=2)
        print(f'  JSON: {json_path}')
    except Exception as e:
        print(f'  JSON error: {e}')


def generate_summary_report(all_results):
    """Generate a summary report across all locations."""
    
    summary_data = []
    total_reviews = 0
    
    for location_name, reviews, coordinates, output_name in all_results:
        rating_sum = 0
        rating_count = 0
        
        for review in reviews:
            try:
                rating = float(review.get('rating', 0))
                rating_sum += rating
                rating_count += 1
            except:
                pass
        
        avg_rating = rating_sum / rating_count if rating_count > 0 else 0
        total_reviews += len(reviews)
        
        summary_data.append({
            'Location': location_name,
            'Reviews': len(reviews),
            'Avg Rating': f'{avg_rating:.2f}' if avg_rating > 0 else 'N/A',
            'Latitude': coordinates.get('latitude', ''),
            'Longitude': coordinates.get('longitude', '')
        })
    
    # Save summary to Excel
    summary_df = pd.DataFrame(summary_data)
    summary_path = os.path.join(DriverLocation, 'locations', 'SUMMARY.xlsx')
    try:
        summary_df.to_excel(summary_path, index=False)
        print(f'\n✓ Summary saved to: {summary_path}')
    except:
        pass
    
    print(f'\n{"="*60}')
    print('SCRAPING SUMMARY')
    print(f'{"="*60}')
    print(f'Total locations: {len(all_results)}')
    print(f'Total unique reviews: {total_reviews}')
    print(summary_df.to_string(index=False))


def main():
    """Main entry point for multi-location scraping."""
    
    # Load locations from JSON
    try:
        with open('locations.json', 'r') as f:
            config = json.load(f)
        locations = config.get('locations', [])
    except FileNotFoundError:
        print('Error: locations.json not found')
        return
    except json.JSONDecodeError:
        print('Error: Invalid JSON in locations.json')
        return
    
    if not locations:
        print('No locations configured in locations.json')
        return
    
    print(f'\nStarting scrape for {len(locations)} locations...')
    print(f'Started at: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    
    all_results = []
    
    for location in locations:
        location_name, reviews, coordinates, output_name = scrape_location(location)
        all_results.append((location_name, reviews, coordinates, output_name))
        
        # Save individual location output
        save_location_output(location_name, reviews, coordinates, output_name)
        
        # Small delay between locations to be respectful to Google
        time.sleep(2)
    
    # Generate summary report
    generate_summary_report(all_results)
    
    print(f'\nCompleted at: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')


if __name__ == '__main__':
    main()
