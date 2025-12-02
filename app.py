import time
import os
import re

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.webdriver import WebDriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from openpyxl import Workbook
import pandas as pd
from bs4 import BeautifulSoup

from env import URL, DriverLocation


def get_data(driver, dataStructreType):
    """Extract reviews and keywords using BeautifulSoup to parse page HTML.

    Returns tuple: (list_of_rows, keywords_list)
    """
    print('extracting reviews...')
    lst_data = []
    seen = set()

    # Expand all "More" buttons
    print('  Expanding truncated review text...')
    try:
        more_btns = driver.find_elements(By.XPATH, "//button[contains(text(), 'More')]")
        print(f'    Found {len(more_btns)} More buttons')
        for btn in more_btns:
            try:
                if btn.is_displayed():
                    driver.execute_script('arguments[0].click();', btn)
                    time.sleep(0.05)
            except:
                pass
    except Exception as e:
        print(f'    Error: {e}')

    # Get page HTML
    page_html = driver.page_source
    soup = BeautifulSoup(page_html, 'html.parser')

    # Strategy 1: look for rating information in aria-label attributes or text like 'out of 5' or 'stars'
    print('  Parsing HTML with BeautifulSoup (heuristics)...')

    review_count = 0

    # Helper: date-like regex
    month_names = r"Jan(uary)?|Feb(ruary)?|Mar(ch)?|Apr(il)?|May|Jun(e)?|Jul(y)?|Aug(ust)?|Sep(t)?|Oct(ober)?|Nov(ember)?|Dec(ember)?"
    date_re = re.compile(rf"(\b({month_names})\b.*\d{{4}})|(\b\d+\s+{month_names}\b)|(\b\d+\s+ago\b)|\b(today|yesterday)\b", re.I)

    # 1) Find elements with aria-label that mention stars or rating
    rating_els = [el for el in soup.find_all(attrs={}) if el.has_attr('aria-label') and re.search(r"(star|stars|out of 5|rated|rating)", el['aria-label'], re.I)]
    print(f'    Found {len(rating_els)} elements with aria-label rating text')

    # Use simpler strategy: extract directly from data-review-id divs (most reliable)
    reviews_by_id = soup.select('div[data-review-id]')
    print(f'    Found {len(reviews_by_id)} reviews by data-review-id')
    
    for review_container in reviews_by_id:
        try:
            # Extract NAME from d4r55
            name = ''
            name_el = review_container.select_one('div.d4r55')
            if name_el:
                name = name_el.get_text(strip=True)
            
            if not name:
                name = 'Anonymous'
            
            # Extract RATING from aria-label
            rating = '-'
            for el in review_container.find_all(attrs={'aria-label': re.compile(r'star', re.I)}):
                al = el.get('aria-label', '')
                m = re.search(r'(\d+(?:\.\d+)?)\s*star', al, re.I)
                if m:
                    rating = m.group(1)
                    break
            
            # Extract DATE and COMMENT from all text
            all_text = review_container.get_text()
            
            # Find date: patterns like "a week ago", "week ago", "2 weeks ago", "today", "yesterday"
            date = ''
            # Try pattern 1: "(number) (unit) ago" or "(a/an) (unit) ago"
            date_match = re.search(r'(a\s+)?(\d+)?\s*(hour|day|week|month|year)s?\s+ago', all_text, re.I)
            if date_match:
                date = date_match.group(0).strip()
            else:
                # Fallback: look for "today" or "yesterday"
                today_match = re.search(r'\b(today|yesterday)\b', all_text, re.I)
                if today_match:
                    date = today_match.group(0).strip()
            
            # Extract COMMENT: after date marker, before "Like"/"Share" buttons or end
            comment = ''
            if date:
                # Find position of date in text
                date_pos = all_text.find(date)
                if date_pos != -1:
                    # Text after the date
                    after_date = all_text[date_pos + len(date):]
                    # Remove "New" marker if present
                    after_new = re.sub(r'^\s*New\s*', '', after_date, flags=re.I)
                    # Remove "Like", "Share", timestamp (0:XX), and everything after
                    comment = re.sub(r'(Like|Share|(?:0:\d{2})+).*$', '', after_new, flags=re.I).strip()
                    # Clean up unicode glyphs (star ratings, emoji-like icons)
                    comment = re.sub(r'[\ue000-\uf8ff]', '', comment).strip()
            
            # Dedupe and store
            key = (name, comment, date)
            if key not in seen:
                seen.add(key)
                lst_data.append([name + ' from GoogleMaps', comment, rating, date])
                review_count += 1
        except Exception:
            continue


    # Extract review-topic chips / keywords from the modal
    keywords = []
    try:
        modal = soup.find('div', role='dialog') or soup
        # common chip/button selectors
        chip_selectors = [
            "button[class*='chip']",
            "div[class*='chip']",
            "button[class*='filter']",
            "div[class*='filter']",
            "button[aria-pressed]",
        ]
        for sel in chip_selectors:
            for el in modal.select(sel):
                t = el.get_text(strip=True)
                if t and len(t) < 80 and not re.search(r'Like|Share|Newest|Most relevant|All|More', t, re.I):
                    if t not in keywords:
                        keywords.append(t)

        # fallback: collect short button texts under modal
        for b in modal.find_all('button'):
            t = b.get_text(strip=True)
            if t and len(t) < 80 and not re.search(r'Like|Share|More|All', t, re.I):
                if t not in keywords:
                    keywords.append(t)
    except Exception:
        keywords = []

    return lst_data, keywords


def ifGDRPNotice(driver):
    # check if the domain of the url is consent.google.com
    if 'consent.google.com' in driver.current_url:
        # click on the "I agree" button
        try:
            driver.execute_script('document.getElementsByTagName("form")[0].submit()')
        except:
            pass
    return


def ifPageIsFullyLoaded(driver):
    # check if the page fully loaded including js
    try:
        return driver.execute_script('return document.readyState') != 'complete'
    except:
        return False


def counter():
    dataStructreType = 1
    try:
        result = driver.find_element(By.XPATH, '//body/div[2]/div[3]/div[8]/div[9]/div[1]/div[1]/div[1]/div[2]/div[1]/div[1]/div[1]/div[1]/div[2]/div[1]/div[1]/div[2]').find_element(By.CLASS_NAME, 'fontBodySmall').text
    except:
        try:
            dataStructreType = 2
            result = driver.find_element(By.XPATH, '//body/div[2]/div[3]/div[8]/div[9]/div[1]/div[1]/div[1]/div[2]/div[1]/div[1]/div[1]/div[1]/div[2]/div[2]/div[1]/div[2]').find_element(By.CLASS_NAME, 'fontBodySmall').text
        except:
            print('Warning: Could not find review counter element. Using default value.')
            return 1, 1
    result = result.replace(',', '')
    result = result.replace('.', '')
    result = result.split(' ')
    result = result[0].split('\n')
    try:
        return int(int(result[0]) / 10) + 1, dataStructreType
    except:
        print('Warning: Could not parse counter. Using default value.')
        return 1, dataStructreType

def open_reviews_panel(driver):
    """Click 'More reviews (N)' button to open the full reviews dialog."""
    try:
        # Primary: click button containing 'More reviews'
        try:
            btn = driver.find_element(By.XPATH, "//button[contains(., 'More reviews')]")
            btn.click()
            time.sleep(2)
            return True
        except:
            pass

        # Fallback: click element with text 'More reviews'
        try:
            el = driver.find_element(By.XPATH, "//*[contains(text(), 'More reviews')]")
            el.click()
            time.sleep(2)
            return True
        except:
            pass
    except Exception:
        return False
    return False


def scrolling(counter):
    """Scroll the reviews panel to load more reviews with multiple strategies."""
    print('scrolling...')
    
    # Increased iterations and timeouts to allow more data loading
    max_iterations = 30  # Be more aggressive
    
    # Helper: try to find the reviews scrollable container (modal)
    def find_reviews_container():
        selectors = [
            "div[role='dialog'] div[tabindex='-1']",
            "div[role='dialog'] div[class*='section-scrollbox']",
            "div[role='dialog'] div[class*='m6QErb']",
            "div[role='dialog']",
            "div[aria-modal='true']",
            "div[jsname='lzXdId']",  # Google Maps reviews panel container
        ]
        for sel in selectors:
            try:
                els = driver.find_elements(By.CSS_SELECTOR, sel)
                for el in els:
                    try:
                        if el.is_displayed():
                            return el
                    except:
                        return el
            except:
                continue
        return None

    container = find_reviews_container()
    if container is None:
        print('  Modal not found. Reviews may already be loaded.')
    else:
        print('  Found reviews modal container. Scrolling aggressively...')

    for i in range(max_iterations):
        # Strategy 1: Multiple scrolls to bottom
        try:
            if container is not None:
                # Scroll to bottom multiple times
                for _ in range(5):
                    driver.execute_script('arguments[0].scrollTop = arguments[0].scrollHeight', container)
                    time.sleep(0.2)
            else:
                # Aggressive window scroll
                driver.execute_script('window.scrollTo(0, document.body.scrollHeight)')
                time.sleep(0.15)
        except:
            pass

        # Strategy 2: Send keyboard navigation keys
        try:
            if container is not None:
                for _ in range(3):
                    container.send_keys(Keys.END)
                    time.sleep(0.15)
        except:
            pass

        time.sleep(0.5)

        # Strategy 3: Expand all "More" buttons
        try:
            if container is not None:
                more_btns = container.find_elements(By.XPATH, ".//button[contains(text(), 'More')]")
            else:
                more_btns = driver.find_elements(By.XPATH, "//button[contains(text(), 'More')]")

            for btn in more_btns[:10]:  # Limit to first 10 to avoid too many clicks
                try:
                    driver.execute_script('arguments[0].scrollIntoView(true);', btn)
                    time.sleep(0.05)
                    driver.execute_script('arguments[0].click();', btn)
                    time.sleep(0.15)
                except:
                    pass
        except:
            pass

        # Every 5 iterations, wait longer to allow Google to load more reviews
        if i % 5 == 4:
            time.sleep(1.0)
        else:
            time.sleep(0.3)

        if (i + 1) % 10 == 0:
            print(f'  Scroll iteration {i}: continuing...')


def set_sort_newest(driver):
    """Click the Sort button and choose Newest."""
    try:
        # Click the "Sort" button
        try:
            sort_btn = driver.find_element(By.XPATH, "//button[contains(., 'Sort')]")
            sort_btn.click()
            time.sleep(0.7)
        except:
            pass

        # Click "Newest" option in the dropdown
        try:
            newest_opt = driver.find_element(By.XPATH, "//div[.='Newest']")
            newest_opt.click()
            time.sleep(1.5)
            return True
        except:
            pass
    except Exception:
        pass
    return False


def set_sort_most_relevant(driver):
    """Open Sort dropdown and choose 'Most relevant' if available."""
    try:
        try:
            sort_btn = driver.find_element(By.XPATH, "//button[contains(., 'Sort')]")
            sort_btn.click()
            time.sleep(0.6)
        except:
            pass

        try:
            mr = driver.find_element(By.XPATH, "//div[.='Most relevant']")
            mr.click()
            time.sleep(1.0)
            return True
        except:
            return False
    except Exception:
        return False



def write_to_xlsx(data):
    print('write to excel...')
    cols = ["name", "comment", 'rating', 'date']
    df = pd.DataFrame(data, columns=cols)

    # ensure output directory exists
    try:
        os.makedirs(DriverLocation, exist_ok=True)
    except:
        pass

    out_path = os.path.join(DriverLocation, 'OneLocation.xlsx')
    df.to_excel(out_path, index=False)


def clean_reviews(data_list):
    """Clean and normalize extracted review rows.

    Input: list of [name, comment, rating, date]
    Returns: cleaned list of rows
    """
    cleaned = []
    for row in data_list:
        try:
            # support format: [name, comment, rating, date]
            if len(row) == 4:
                name, comment, rating, date = row
            else:
                # skip malformed rows
                continue
        except ValueError:
            # skip malformed rows
            continue

        # Normalize types and strip
        if not isinstance(name, str):
            name = str(name or '')
        if not isinstance(comment, str):
            comment = str(comment or '')
        if not isinstance(rating, str):
            rating = str(rating or '')
        if not isinstance(date, str):
            date = str(date or '')

        name = name.strip()
        comment = comment.strip()
        rating = rating.strip()
        date = date.strip()

        # Remove our appended marker
        name = re.sub(r"\s+from\s+GoogleMaps$", '', name, flags=re.I).strip()

        # Remove common metadata tokens from name and comment
        def strip_meta(s):
            s = re.sub(r"Local\s*Guide(?:\s*\?\s*\d+\s*reviews)?", '', s, flags=re.I)
            s = re.sub(r"\?", '', s)
            s = re.sub(r"\u200e|\u202a|\u202c", '', s)  # directional marks
            s = re.sub(r"\b\d+\s*reviews?\b", '', s, flags=re.I)
            s = re.sub(r"\d+\s*photos?", '', s, flags=re.I)
            s = re.sub(r"[\u25cf\u2022\u2023]", '', s)  # bullets
            s = re.sub(r"\s{2,}", ' ', s)
            return s.strip(' -–—:,.')

        name = strip_meta(name)
        comment = strip_meta(comment)

        # If comment accidentally contains the name at the start, remove it
        if name and comment.startswith(name):
            comment = comment[len(name):].strip(' -–—:,')

        # Normalize rating to float when possible
        norm_rating = None
        if rating and rating not in ['-', '']:
            m = re.search(r"(\d+(?:\.\d+)?)", rating)
            if m:
                try:
                    norm_rating = float(m.group(1))
                except:
                    norm_rating = None
        # If still None, try to extract from comment (e.g., '5' or '5 stars')
        if norm_rating is None:
            m2 = re.search(r"(\d(?:\.\d)?)\s*(?:out of 5|stars?)", comment, re.I)
            if m2:
                try:
                    norm_rating = float(m2.group(1))
                except:
                    norm_rating = None

        # Normalize date: lowercase and basic cleanup
        date = date.replace('\u2019', "'")
        date = re.sub(r"\s+", ' ', date).strip()
        if date.lower() in ['-', '']:
            date = ''

        cleaned.append([name, comment, norm_rating if norm_rating is not None else '', date])

    return cleaned


if __name__ == "__main__":

    print('starting...')
    options = webdriver.ChromeOptions()
    # options.add_argument("--headless")  # show browser or not
    options.add_argument("--lang=en-US")
    options.add_experimental_option('prefs', {'intl.accept_languages': 'en,en_US'})
    driver = webdriver.Chrome(options=options)

    driver.get(URL)
    
    while ifPageIsFullyLoaded(driver):
        time.sleep(1)
        
    ifGDRPNotice(driver)
    
    while ifPageIsFullyLoaded(driver):
        time.sleep(1)

    # Wait a bit more for content to render
    time.sleep(3)

    # Open the reviews panel (click the reviews count) and set sort to Newest
    try:
        opened = open_reviews_panel(driver)
        if opened:
            time.sleep(1.5)
            try:
                set_sort_newest(driver)
                time.sleep(1.5)
            except:
                pass
            # Dump page source after opening the reviews modal for inspection
            try:
                os.makedirs(DriverLocation, exist_ok=True)
                ps_path = os.path.join(DriverLocation, 'page_source.html')
                with open(ps_path, 'w', encoding='utf-8') as fh:
                    fh.write(driver.page_source)
                print(f'Saved page source to {ps_path}')
            except Exception as e:
                print('Could not save page source:', e)
        else:
            print('Warning: Could not open reviews panel via heuristics.')
    except Exception:
        pass

    counter = counter()
    scrolling(counter[0])

    data, keywords = get_data(driver, counter[1])

    # parse coordinates from current URL
    current_url = driver.current_url
    lat = None
    lon = None
    try:
        m = re.search(r"@(-?\d+\.\d+),(-?\d+\.\d+)", current_url)
        if m:
            lat = float(m.group(1))
            lon = float(m.group(2))
        else:
            m2 = re.search(r"[?&]ll=(-?\d+\.\d+),(-?\d+\.\d+)", current_url)
            if m2:
                lat = float(m2.group(1))
                lon = float(m2.group(2))
    except:
        lat = None
        lon = None

    driver.close()

    # Clean extracted data before writing
    try:
        cleaned = clean_reviews(data)
    except Exception:
        cleaned = data

    # Add coordinates to every row for Excel
    df = pd.DataFrame(cleaned, columns=["name", "comment", 'rating', 'date'])
    df['latitude'] = lat if lat is not None else ''
    df['longitude'] = lon if lon is not None else ''

    # write excel (handle permission issues by falling back to timestamped filename)
    try:
        os.makedirs(DriverLocation, exist_ok=True)
    except:
        pass
    out_path = os.path.join(DriverLocation, 'OneLocation.xlsx')
    try:
        df.to_excel(out_path, index=False)
    except PermissionError:
        import datetime
        stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        out_path = os.path.join(DriverLocation, f'OneLocation_{stamp}.xlsx')
        try:
            df.to_excel(out_path, index=False)
            print('Wrote to alternate Excel path:', out_path)
        except Exception as e:
            print('Failed to write Excel:', e)
    except Exception as e:
        print('Failed to write Excel:', e)

    # write JSON with metadata
    json_out = os.path.join(DriverLocation, 'OneLocation.json')
    payload = {
        'source_url': URL,
        'coordinates': {'latitude': lat, 'longitude': lon},
        'keywords': keywords,
        'reviews': [
            {'name': r[0], 'comment': r[1], 'rating': r[2], 'date': r[3]} for r in cleaned
        ]
    }
    try:
        with open(json_out, 'w', encoding='utf-8') as jf:
            import json
            json.dump(payload, jf, ensure_ascii=False, indent=2)
    except Exception as e:
        print('Could not write JSON:', e)
    print('Done!')

