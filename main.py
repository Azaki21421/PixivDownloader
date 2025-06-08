import concurrent.futures
import os
import re
import shutil
import sys
import time
import zipfile

import requests
from bs4 import BeautifulSoup
from requests.exceptions import JSONDecodeError
from tqdm import tqdm

# --- Configuration ---
PHPSESSID = ""  # <<< IMPORTANT: Insert your PHPSESSID here if you encounter issues
#     Especially for R-18 content or rate limiting.
#     Go to pixiv.net, log in, open Dev Tools (F12) -> Application -> Cookies -> pixiv.net
#     Find the 'PHPSESSID' cookie and copy its value.
#     MAKE SURE THIS IS UP-TO-DATE! It's the most common cause of HTML responses instead of JSON.
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "https://www.pixiv.net/",
    "Cookie": f"PHPSESSID={PHPSESSID}" if PHPSESSID else ""
}

# --- Multi-threading configuration ---
MAX_DOWNLOAD_WORKERS = 10  # Number of concurrent image downloads. Adjust as needed (5-20 usually good).


# --- Utility Functions ---
def sanitize_filename(name):
    """Removes invalid characters from a string to be used as a filename."""
    return re.sub(r'[\\/*?:"<>|]', "", name)


def download_image_threaded(url, path):
    """Downloads an image from a URL to a specified path."""
    try:
        r = requests.get(url, headers=HEADERS, stream=True, timeout=15)
        r.raise_for_status()

        with open(path, 'wb') as f:
            for chunk in r.iter_content(8192):
                f.write(chunk)
        return True, f"Downloaded {os.path.basename(path)}"
    except requests.exceptions.RequestException as e:
        return False, f"Error downloading {url}: {e}"
    except Exception as e:
        return False, f"An unexpected error occurred while downloading {url}: {e}"


def zip_folder(folder_path, zip_path):
    """Compresses a folder into a zip archive and optionally removes the original folder."""
    if not os.path.exists(folder_path):
        print(f"Folder '{folder_path}' does not exist. Skipping archiving.")
        return

    zip_full_path = zip_path if zip_path.endswith(".zip") else zip_path + ".zip"
    print(f"Creating archive: {zip_full_path}")
    try:
        if not os.listdir(folder_path):
            print(f"Folder '{folder_path}' is empty. Not creating an archive.")
            shutil.rmtree(folder_path)
            print(f"Removed empty temporary folder: {folder_path}")
            return

        with zipfile.ZipFile(zip_full_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, _, files in os.walk(folder_path):
                for file in files:
                    full_path = os.path.join(root, file)
                    rel_path = os.path.relpath(full_path, start=os.path.dirname(folder_path))
                    zf.write(full_path, arcname=rel_path)
        print(f"Archived into {zip_full_path}")
        shutil.rmtree(folder_path)
        print(f"Removed temporary folder: {folder_path}")
    except Exception as e:
        print(f"Error zipping folder {folder_path}: {e}")


# --- Core Parsing Functions ---
def parse_post(post_url):
    """
    Parses a single Pixiv artwork post to extract its title and image URLs.
    Leverages Pixiv's /ajax/illust/{id}/pages API for image URLs.
    Fetches HTML for the title using the provided CSS selector.
    """
    print(f"\n--- Processing post: {post_url} ---")

    illust_id_match = re.search(r'/artworks/(\d+)', post_url)
    if not illust_id_match:
        print(f"Error: Invalid Pixiv artwork URL format: {post_url}")
        return "Untitled", []
    illust_id = illust_id_match.group(1)

    title = "Untitled"
    image_urls = []

    html_soup = None

    # --- Attempt to get title from /ajax/illust/{id} API first (more reliable) ---
    illust_details_api_url = f"https://www.pixiv.net/ajax/illust/{illust_id}?lang=en"
    print(f"Querying Pixiv artwork details API for title: {illust_details_api_url}")
    api_headers = HEADERS.copy()
    api_headers["Referer"] = post_url

    try:
        r_illust_details_api = requests.get(illust_details_api_url, headers=api_headers, timeout=10)
        r_illust_details_api.raise_for_status()
        illust_details_data = r_illust_details_api.json()

        if illust_details_data and not illust_details_data.get("error"):
            api_title = illust_details_data.get("body", {}).get("title")
            if api_title:
                title = sanitize_filename(api_title)
                print(f"Parsed title from Illust API: {title}")
        else:
            print(f"Illust details API failed or returned error for {illust_id}.")

    except (requests.exceptions.RequestException, JSONDecodeError) as e:
        print(
            f"Warning: Could not fetch title from Illust details API for {illust_id}: {e}. Falling back to HTML parsing.")
    except Exception as e:
        print(f"Warning: Unexpected error fetching Illust details API for title: {e}. Falling back to HTML parsing.")

    # --- HTML parsing for title fallback (if API failed or no title from API) ---
    if title == "Untitled":  # Only fetch HTML if title wasn't found by API
        print(f"Attempting to fetch title from artwork HTML: {post_url}")
        try:
            r_html = requests.get(post_url, headers=HEADERS, timeout=10)
            r_html.raise_for_status()
            html_soup = BeautifulSoup(r_html.text, "html.parser")

            title_tag = html_soup.select_one('main h1')
            if title_tag:
                title = title_tag.text.strip()
                title = sanitize_filename(title)
            else:
                title_tag_meta = html_soup.find("title")
                if title_tag_meta:
                    title = title_tag_meta.text.split(" - ")[0].strip()
                    title = sanitize_filename(title)
            print(f"Parsed title from HTML fallback: {title}")
        except requests.exceptions.RequestException as e:
            print(f"Warning: Could not fetch HTML for title from {post_url}: {e}. Using default title.")
        except Exception as e:
            print(f"Warning: Error parsing title from HTML: {e}. Using default title.")

    pages_api_url = f"https://www.pixiv.net/ajax/illust/{illust_id}/pages?lang=en"
    print(f"Querying Pixiv API for image data (pages): {pages_api_url}")

    try:
        r_pages_api = requests.get(pages_api_url, headers=api_headers, timeout=10)
        r_pages_api.raise_for_status()

        try:
            pages_api_data = r_pages_api.json()
        except JSONDecodeError as e:
            print(f"JSONDecodeError when processing {pages_api_url}: {e}")
            print(f"Raw response content that failed to decode (first 500 chars): {r_pages_api.text[:500]}...")
            print("This usually means Pixiv sent HTML instead of JSON (e.g., CAPTCHA, login page, or error).")
            print("Please ensure your PHPSESSID is correct and up-to-date in the script.")
            pages_api_data = None

        if pages_api_data and not pages_api_data.get("error"):
            for page in pages_api_data.get("body", []):
                if "urls" in page and "original" in page["urls"]:
                    image_urls.append(page["urls"]["original"])
            print(f"Found {len(image_urls)} original image URLs via Pixiv API for illust ID {illust_id}.")
        else:
            print(
                f"Pixiv /pages API failed for illust ID {illust_id} or returned an error. Attempting to extract images from HTML as a fallback (less reliable)...")
            # If html_soup wasn't already fetched for title, fetch it now for image fallback
            if html_soup is None:
                try:
                    r_html_fallback = requests.get(post_url, headers=HEADERS, timeout=10)
                    r_html_fallback.raise_for_status()
                    html_soup = BeautifulSoup(r_html_fallback.text, "html.parser")
                except requests.exceptions.RequestException as e:
                    print(f"Warning: Could not fetch HTML for image fallback from {post_url}: {e}.")

            if html_soup:
                all_img_tags = html_soup.find_all("img", src=re.compile(r'i\.pximg\.net/img-(master|original)/'))
                all_img_tags.extend(
                    html_soup.find_all("img", attrs={"data-src": re.compile(r'i\.pximg\.net/img-(master|original)/')}))

                temp_image_urls = []
                for img_tag in all_img_tags:
                    src = img_tag.get("src") or img_tag.get("data-src")
                    if src:
                        processed_src = src.replace("c/250x250_80_a2/", "").replace("custom-thumb", "img-original")
                        processed_src = re.sub(r"/img-master/", "/img-original/", processed_src)
                        processed_src = re.sub(r"_master\d+\.(jpg|png|gif)", r".\1", processed_src)
                        temp_image_urls.append(processed_src)
                image_urls = list(dict.fromkeys(temp_image_urls))
                print(f"Fallback HTML parsing found {len(image_urls)} images.")
            else:
                print("No HTML available for fallback image parsing.")

        return title, image_urls

    except requests.exceptions.RequestException as e:
        print(f"Error fetching /pages API data for illust ID {illust_id}: {e}")
        return title, []
    except Exception as e:
        print(f"An unexpected error occurred while processing /pages API data for illust ID {illust_id}: {e}")
        return title, []


def parse_user(user_url):
    """
    Parses a Pixiv user's profile to get all their artwork URLs.
    Uses Pixiv's /ajax/user/{user_id}/profile/all API and handles its potential new list structure.
    """
    print(f"\n--- Processing user: {user_url} ---")
    user_id_match = re.search(r'/users/(\d+)', user_url)
    if not user_id_match:
        raise ValueError(f"Invalid Pixiv user URL format: {user_url}")
    user_id = user_id_match.group(1)

    all_posts = []

    profile_api_url = f"https://www.pixiv.net/ajax/user/{user_id}/profile/all?lang=en"
    print(f"Attempting to fetch user artworks list via: {profile_api_url}")

    user_api_headers = HEADERS.copy()
    user_api_headers["Referer"] = f"https://www.pixiv.net/en/users/{user_id}/artworks"

    try:
        r = requests.get(profile_api_url, headers=user_api_headers, timeout=15)
        r.raise_for_status()

        try:
            json_data = r.json()
        except JSONDecodeError as e:
            print(f"JSONDecodeError when parsing user profile API for user {user_id}: {e}")
            print(f"Raw response content that failed to decode (first 500 chars): {r.text[:500]}...")
            print("This often means Pixiv returned HTML (e.g., CAPTCHA) instead of JSON for the user profile API.")
            print("Please ensure your PHPSESSID is correct and up-to-date in the script.")
            return []

        if json_data.get("error"):
            print(
                f"Pixiv profile API returned an error for user {user_id}: {json_data.get('message', 'Unknown error')}")
            return []

        illusts_data = json_data.get("body", {}).get("illusts")
        manga_data = json_data.get("body", {}).get("manga")

        if illusts_data:
            if isinstance(illusts_data, dict):
                all_posts.extend(illusts_data.keys())
            elif isinstance(illusts_data, list):
                for item in illusts_data:
                    if isinstance(item, dict) and 'id' in item:
                        all_posts.append(item['id'])
            else:
                print(f"Warning: Unexpected type for 'illusts' data: {type(illusts_data)}")

        if manga_data:
            if isinstance(manga_data, dict):
                all_posts.extend(manga_data.keys())
            elif isinstance(manga_data, list):
                for item in manga_data:
                    if isinstance(item, dict) and 'id' in item:
                        all_posts.append(item['id'])
            else:
                print(f"Warning: Unexpected type for 'manga' data: {type(manga_data)}")

        all_posts = list(dict.fromkeys(all_posts))

    except requests.exceptions.HTTPError as e:
        print(f"HTTP Error {e.response.status_code} fetching user profile API for user {user_id}: {e}")
        print(
            "This might indicate the API endpoint has changed, access is restricted, or the user has no public content.")
    except requests.exceptions.RequestException as e:
        print(f"Connection Error fetching user profile API for user {user_id}: {e}")
    except Exception as e:
        print(f"An unexpected error occurred while fetching user profile for user {user_id}: {e}")

    artwork_urls = [f"https://www.pixiv.net/artworks/{pid}" for pid in all_posts]
    print(f"Found {len(artwork_urls)} total artwork URLs for user {user_id}.")
    return artwork_urls


# --- Main Execution Logic ---
def main():
    """Main function to handle user input and orchestrate the scraping process."""
    print("--- Pixiv Scraper ---")
    print("Remember to insert your PHPSESSID in the script if you face issues with R-18 content or rate limits.")
    print("Press Ctrl+C at any time to stop the process and archive downloaded files.")
    url = input("Enter Pixiv link (artwork post or user profile): ").strip()

    current_download_folder = None
    current_root_folder = None

    try:
        if "/artworks/" in url:
            title, images = parse_post(url)
            if not images:
                print("No images found for this post. It might be private, deleted, or the API structure has changed.")
                return

            folder = sanitize_filename(title)
            current_download_folder = folder
            os.makedirs(folder, exist_ok=True)
            print(f"Starting download for '{title}' into folder '{folder}' with {len(images)} images...")

            with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_DOWNLOAD_WORKERS) as executor:
                future_to_image = {
                    executor.submit(download_image_threaded, img_url, os.path.join(folder,
                                                                                   f"{i + 1:02d}{os.path.splitext(img_url)[1].split('?')[0] or '.jpg'}")):
                        img_url
                    for i, img_url in enumerate(images)
                }
                for future in tqdm(concurrent.futures.as_completed(future_to_image), total=len(images),
                                   desc="Downloading images"):
                    success, message = future.result()
                    if not success:
                        print(f"Error: {message}")

            zip_folder(folder, folder)
            print(f"Download for '{title}' completed.")

        elif "/users/" in url:
            mode = input("Download into separate folders for each post? (y/n): ").strip().lower() == 'y'

            post_urls = parse_user(url)
            if not post_urls:
                print("No posts found for this user, or an error occurred while fetching user data.")
                return

            user_id_for_folder = url.split('/')[-1]
            if user_id_for_folder.isdigit():
                root_folder_name = f"Pixiv_User_{user_id_for_folder}"
            else:
                root_folder_name = f"Pixiv_User_{sanitize_filename(user_id_for_folder.split('/')[0])}"

            current_root_folder = root_folder_name
            os.makedirs(root_folder_name, exist_ok=True)
            print(f"Found {len(post_urls)} posts for the user. Starting download into '{root_folder_name}'...")

            for post_url_item in tqdm(post_urls, desc="Processing user posts"):
                try:
                    title, images = parse_post(post_url_item)
                except Exception as e:
                    print(f"Error parsing post {post_url_item}: {e}. Skipping.")
                    continue

                if not images:
                    print(f"No images found for post {post_url_item}. Skipping.")
                    continue

                download_tasks = []
                if mode:
                    subfolder = os.path.join(root_folder_name, sanitize_filename(title))
                    os.makedirs(subfolder, exist_ok=True)
                    for i, img_url in enumerate(images):
                        ext = os.path.splitext(img_url)[1].split("?")[0] or ".jpg"
                        filename = os.path.join(subfolder, f"{i + 1:02d}{ext}")
                        download_tasks.append((img_url, filename))
                else:
                    for i, img_url in enumerate(images):
                        ext = os.path.splitext(img_url)[1].split("?")[0] or ".jpg"
                        post_id = post_url_item.split('/')[-1]
                        filename = os.path.join(root_folder_name,
                                                f"{sanitize_filename(title)}_{post_id}_{i + 1:02d}{ext}")
                        download_tasks.append((img_url, filename))

                if download_tasks:
                    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_DOWNLOAD_WORKERS) as executor:
                        future_to_image = {
                            executor.submit(download_image_threaded, img_url, filename): img_url
                            for img_url, filename in download_tasks
                        }
                        for future in tqdm(concurrent.futures.as_completed(future_to_image), total=len(download_tasks),
                                           desc=f"Downloading '{title[:20]}...'"):
                            success, message = future.result()
                            if not success:
                                print(f"Error: {message}")

                time.sleep(0.5)

            zip_folder(root_folder_name, root_folder_name)
            print(f"All downloads for user '{url}' completed.")

        else:
            print(
                "Unrecognized Pixiv link. Please provide an artwork post URL (e.g., https://www.pixiv.net/artworks/...) or a user profile URL (e.g., https://www.pixiv.net/users/...).")

    except KeyboardInterrupt:
        print("\nDownload interrupted by user (Ctrl+C).")
        if current_download_folder and os.path.exists(current_download_folder):
            print(f"Archiving partially downloaded single post folder: '{current_download_folder}'...")
            zip_folder(current_download_folder, current_download_folder)
        elif current_root_folder and os.path.exists(current_root_folder):
            print(f"Archiving partially downloaded user folder: '{current_root_folder}'...")
            zip_folder(current_root_folder, current_root_folder)
        else:
            print("No active download folder to archive.")
        sys.exit(0)
    except Exception as e:
        print(f"\nAn unexpected error occurred: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
