"""
Helper script to format and validate Google Maps URLs for use in locations.json
Usage: python find_urls.py
"""

import json
import re
from urllib.parse import quote

def validate_gmaps_url(url):
    """Check if URL is a valid Google Maps place URL."""
    patterns = [
        r'https://www\.google\.com/maps/place/',
        r'https://maps\.google\.com/maps/place/',
        r'https://goo\.gl/maps/',
    ]
    return any(re.match(pattern, url) for pattern in patterns)


def extract_place_from_url(url):
    """Try to extract place name from URL."""
    # Format: https://www.google.com/maps/place/PLACE_NAME/@lat,lon,...
    match = re.search(r'/place/([^/@]+)', url)
    if match:
        place = match.group(1).replace('+', ' ')
        return place
    return None


def add_location_to_config(name, url, output_name=None):
    """Add a location to locations.json."""
    
    if not validate_gmaps_url(url):
        print(f"❌ Invalid URL format: {url}")
        return False
    
    if not output_name:
        # Generate output_name from location name
        output_name = re.sub(r'[^a-zA-Z0-9]', '', name.replace(' ', ''))
    
    location_entry = {
        "name": name,
        "url": url,
        "output_name": output_name
    }
    
    # Load existing config
    try:
        with open('locations.json', 'r') as f:
            config = json.load(f)
    except FileNotFoundError:
        config = {"locations": []}
    
    # Check if location already exists
    for loc in config['locations']:
        if loc['output_name'] == output_name:
            print(f"⚠️  Location '{output_name}' already exists in config")
            return False
    
    # Add new location
    config['locations'].append(location_entry)
    
    # Save updated config
    with open('locations.json', 'w') as f:
        json.dump(config, f, indent=2)
    
    print(f"✓ Added: {name}")
    print(f"  Output folder: {output_name}")
    return True


def list_current_locations():
    """Show all locations currently in config."""
    try:
        with open('locations.json', 'r') as f:
            config = json.load(f)
    except FileNotFoundError:
        print("locations.json not found")
        return
    
    locations = config.get('locations', [])
    print(f"\nCurrent locations ({len(locations)}):")
    print("-" * 60)
    for i, loc in enumerate(locations, 1):
        print(f"{i}. {loc['name']}")
        print(f"   Folder: {loc['output_name']}")
        print()


def interactive_mode():
    """Interactive mode to add locations."""
    print("\n" + "="*60)
    print("Google Maps Location Finder")
    print("="*60)
    
    list_current_locations()
    
    while True:
        print("\nOptions:")
        print("1. Add a new location")
        print("2. List current locations")
        print("3. Exit")
        
        choice = input("\nChoose option (1-3): ").strip()
        
        if choice == '1':
            print("\n--- Add New Location ---")
            name = input("Location name (e.g., 'Klyde Warren Park'): ").strip()
            url = input("Google Maps URL: ").strip()
            
            if not name or not url:
                print("❌ Name and URL are required")
                continue
            
            output_name = input(f"Output folder name [{name}]: ").strip()
            if not output_name:
                output_name = None
            
            add_location_to_config(name, url, output_name)
        
        elif choice == '2':
            list_current_locations()
        
        elif choice == '3':
            print("Bye!")
            break
        
        else:
            print("Invalid choice")


def main():
    """Main entry point."""
    import sys
    
    if len(sys.argv) > 2:
        # Command line mode: python find_urls.py "Place Name" "URL"
        name = sys.argv[1]
        url = sys.argv[2]
        add_location_to_config(name, url)
    else:
        # Interactive mode
        interactive_mode()


if __name__ == '__main__':
    main()
