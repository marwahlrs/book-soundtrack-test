# -*- coding: utf-8 -*-
"""Book_Soundtrack.ipynb"""

"""## Setup and Configuration"""

# Import libraries
import requests
import google.generativeai as genai
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import random
from googleapiclient.discovery import build
import os
import streamlit as st

# API Configuration

GOOGLE_BOOKS_API_KEY = st.secrets["GOOGLE_BOOKS_API_KEY"]
GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
SPOTIFY_CLIENT_ID = st.secrets["SPOTIFY_CLIENT_ID"]
SPOTIFY_CLIENT_SECRET = st.secrets["SPOTIFY_CLIENT_SECRET"]
REDIRECT_URI = st.secrets["REDIRECT_URI"]

# API keys are loaded from environment variables using Streamlit secrets

"""## Fetch Book Summary"""

def get_book_info(title, author):
    """Fetch book information from Google Books API with enhanced debugging and Indonesian support"""
    from urllib.parse import quote
    import json
    
    # Debug print statements visible in Streamlit
    st.write("🔍 Debug: API Request Details")
    st.write(f"Original Title: {title}")
    st.write(f"Original Author: {author}")
    
    # Different search strategies with Indonesian support
    search_strategies = [
        # Strategy 1: Basic search with Indonesian language preference
        {
            "query": quote(f"{title} {author}"),
            "params": "&langRestrict=id&maxResults=10"
        },
        # Strategy 2: Exact title and author with quotes
        {
            "query": quote(f"\"{title}\" inauthor:\"{author}\""),
            "params": "&maxResults=10"
        },
        # Strategy 3: Relaxed search
        {
            "query": quote(f"intitle:{title} inauthor:{author}"),
            "params": "&maxResults=10"
        }
    ]
    
    for strategy in search_strategies:
        try:
            url = f"https://www.googleapis.com/books/v1/volumes?q={strategy['query']}{strategy['params']}&key={GOOGLE_BOOKS_API_KEY}"
            
            # Show the sanitized URL (hiding the API key)
            display_url = url.replace(GOOGLE_BOOKS_API_KEY, "API_KEY_HIDDEN")
            st.write(f"🌐 Trying URL: {display_url}")
            
            response = requests.get(url)
            
            # Show response status
            st.write(f"📡 Response Status Code: {response.status_code}")
            
            # If we get an error status code, show the error
            if response.status_code != 200:
                st.write(f"❌ Error Response: {response.text}")
                continue
                
            data = response.json()
            
            # Show the total results found
            total_items = data.get('totalItems', 0)
            st.write(f"📚 Total results found: {total_items}")
            
            if "items" in data and data["items"]:
                # Show the first few results for debugging
                st.write("📖 First matching book details:")
                book = data["items"][0]["volumeInfo"]
                st.write(json.dumps(book, indent=2))
                
                return {
                    "title": book.get("title", "Unknown Title"),
                    "authors": book.get("authors", ["Unknown Author"]),
                    "summary": book.get("description", "No description available."),
                }
            else:
                st.write("⚠️ No items found in response")
                
        except requests.exceptions.RequestException as e:
            st.write(f"🚫 Request error: {str(e)}")
        except json.JSONDecodeError as e:
            st.write(f"🚫 JSON parsing error: {str(e)}")
        except Exception as e:
            st.write(f"🚫 Unexpected error: {str(e)}")
            
    return None
    
"""## Analyze Book Content"""

def analyze_book_with_gemini(book_info):
    """Analyze book content using Google's Gemini AI"""
    client = genai.Client(api_key=GEMINI_API_KEY)

    prompt = f"""
    You are a music and literature expert. Based on the book details below, extract musical insights that would help create a fitting and emotionally resonant soundtrack.

    Title: {book_info['title']}
    Author(s): {', '.join(book_info['authors'])}
    Summary: {book_info['summary']}

    Please analyze the story and return:

    1. **Emotional Tones** – The dominant emotional qualities of the book
    2. **Genres** – Suitable music genres that match the overall tone and pacing
    3. **Moods** – Key moods or emotional shifts across the book
    4. **Time Period / Cultural Context** – Historical or cultural elements
    5. **Keywords** – 5–7 vivid, descriptive words ideal for searching music

    Respond strictly in this format:
    Emotional Tones: [comma-separated list]
    Genres: [comma-separated list]
    Moods: [comma-separated list]
    Time Period/Cultural Context: [brief description]
    Keywords: [comma-separated list]
    """

    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt
        )
        return response.text
    except Exception as e:
        print(f"Error with Gemini API: {e}")
        return None

def parse_gemini_analysis(analysis_text):
    """Parse the structured response from Gemini into a dictionary"""
    if not analysis_text:
        return None

    try:
        sections = {}
        for line in analysis_text.split('\n'):
            line = line.strip()
            if not line or ':' not in line:
                continue

            section_name, content = line.split(':', 1)
            section_name = section_name.strip()
            content = content.strip()

            if content.startswith('[') and content.endswith(']'):
                content = content[1:-1]
            sections[section_name] = [item.strip() for item in content.split(',')]

        return sections
    except Exception as e:
        print(f"Error parsing Gemini analysis: {e}")
        return None

"""## Generate Spotify Playlist"""

def setup_spotify_client():
    """Set up authenticated Spotify client"""
    try:
        auth_manager = SpotifyOAuth(
            client_id=SPOTIFY_CLIENT_ID,
            client_secret=SPOTIFY_CLIENT_SECRET,
            redirect_uri=REDIRECT_URI,
            scope="playlist-modify-public",
            open_browser=False
        )

        auth_url = auth_manager.get_authorize_url()
        print(f"\nPlease visit this URL to authorize the application:\n{auth_url}")
        print("\nAfter authorizing, paste the redirect URL here:")
        response_url = input().strip()

        code = auth_manager.parse_response_code(response_url)
        token_info = auth_manager.get_access_token(code)

        return spotipy.Spotify(auth=token_info['access_token'])

    except Exception as e:
        print(f"Error in Spotify authentication: {e}")
        return None

def search_spotify_tracks(sp, analysis, max_tracks=15):
    """Search for tracks based on book analysis"""
    if not sp or not analysis:
        return []

    tracks = []
    search_weights = {
        'Emotional Tones': 0.3,
        'Moods': 0.3,
        'Genres': 0.25,
        'Keywords': 0.15
    }

    # Build weighted search queries
    search_queries = []

    # Genre queries
    if 'Genres' in analysis:
        for genre in analysis['Genres']:
            search_queries.append({
                'terms': f'genre:"{genre}"',
                'limit': int(max_tracks * search_weights['Genres'])
            })

    # Emotion-genre combinations
    if 'Emotional Tones' in analysis and 'Genres' in analysis:
        for tone in analysis['Emotional Tones']:
            for genre in analysis['Genres'][:2]:
                search_queries.append({
                    'terms': f'{tone} {genre}',
                    'limit': int(max_tracks * search_weights['Emotional Tones'])
                })

    # Mood queries
    if 'Moods' in analysis:
        for mood in analysis['Moods']:
            search_queries.append({
                'terms': mood,
                'limit': int(max_tracks * search_weights['Moods'])
            })

    # Keyword queries
    if 'Keywords' in analysis:
        for keyword in analysis['Keywords']:
            search_queries.append({
                'terms': keyword,
                'limit': int(max_tracks * search_weights['Keywords'])
            })

    # Execute searches
    for query in search_queries:
        try:
            results = sp.search(
                q=query['terms'],
                type="track",
                limit=query['limit']
            )

            for item in results["tracks"]["items"]:
                track = {
                    "id": item["id"],
                    "name": item["name"],
                    "artist": item["artists"][0]["name"],
                    "album": item["album"]["name"],
                    "uri": item["uri"],
                    "popularity": item["popularity"]
                }
                if track not in tracks:
                    tracks.append(track)

        except Exception as e:
            print(f"Error searching for '{query['terms']}': {e}")
            continue

    # Sort by popularity and return top tracks
    tracks.sort(key=lambda x: x['popularity'], reverse=True)
    return tracks[:max_tracks]

def create_spotify_playlist(sp, book_info, tracks, analysis):
    """Create a Spotify playlist from selected tracks"""
    if not sp or not tracks:
        return None

    try:
        user_id = sp.current_user()["id"]

        # Create playlist with rich metadata
        playlist_name = f"📚 {book_info['title']} - Literary Soundtrack"

        description_elements = []
        if analysis.get('Genres'):
            description_elements.append(f"Genres: {', '.join(analysis['Genres'][:3])}")
        if analysis.get('Moods'):
            description_elements.append(f"Moods: {', '.join(analysis['Moods'][:3])}")

        playlist_description = (
            f"A curated soundtrack for {book_info['title']} "
            f"by {', '.join(book_info['authors'])}. "
            f"{' | '.join(description_elements)}"
        )

        # Create playlist
        playlist = sp.user_playlist_create(
            user_id,
            playlist_name,
            public=True,
            description=playlist_description[:300]
        )

        # Add tracks in batches
        track_uris = [track["uri"] for track in tracks]
        batch_size = 50
        for i in range(0, len(track_uris), batch_size):
            batch = track_uris[i:i + batch_size]
            sp.playlist_add_items(playlist["id"], batch)

        return playlist["external_urls"]["spotify"]

    except Exception as e:
        print(f"Error creating playlist: {e}")
        return None

"""## Interface"""

def display_analysis_results(analysis):
    """Display analysis results in a structured format"""
    st.subheader("📊 Analysis Results")
    st.markdown("=" * 50)

    sections = {
        'Emotional Tones': '🎭 Emotional Tones',
        'Genres': '🎵 Musical Genres',
        'Moods': '🌈 Moods',
        'Time Period/Cultural Context': '📅 Time Period/Cultural Context',
        'Keywords': '🔑 Keywords'
    }

    for section, header in sections.items():
        if section in analysis:
            st.markdown(f"### {header}")
            if isinstance(analysis[section], list):
                for item in analysis[section]:
                    st.write(f"• {item}")
            else:
                st.write(f"• {analysis[section]}")
    st.markdown("=" * 50)

def display_tracks_details(tracks):
    """Display track information in a formatted way"""
    st.subheader("🎵 Selected Tracks")
    st.markdown("=" * 50)

    for i, track in enumerate(tracks, 1):
        popularity_stars = "⭐" * ((track['popularity'] // 20) + 1)
        st.write(f"{i}. {track['name']}")
        st.write(f"   Artist: {track['artist']}")
        st.write(f"   Album: {track['album']}")
        st.write(f"   Popularity: {popularity_stars} ({track['popularity']}/100)")

    st.markdown("=" * 50)

def main():
    st.title("📚 Literary Soundtrack Generator 🎵")
    st.markdown("=" * 50)

    # Get book details
    book_title = st.text_input("Enter the book title:")
    book_author = st.text_input("Enter the book's author:")

    if not book_title or not book_author:
        st.warning("Please enter both the book title and author.")
        return

    # Add debug info
    st.write("Debug Information:")
    st.write(f"Searching for title: '{book_title}'")
    st.write(f"Searching for author: '{book_author}'")
    
    # Fetch book information
    st.write("\n📖 Fetching book information...")
    book_info = get_book_info(book_title, book_author)

    if not book_info:
        st.error("❌ Could not find book information. Please check the title and author.")
        # Add additional debug info
        st.write("Try these troubleshooting steps:")
        st.write("1. Check if the title and author are spelled correctly")
        st.write("2. Try using the English title if available")
        st.write("3. Make sure your API key is valid")
        return

    # Analyze content
    st.write("\n🤖 Analyzing book content...")
    analysis_text = analyze_book_with_gemini(book_info)
    if not analysis_text:
        st.error("❌ Failed to analyze the book.")
        return

    analysis = parse_gemini_analysis(analysis_text)
    if not analysis:
        st.error("❌ Failed to parse the analysis results.")
        return

    # Display analysis
    display_analysis_results(analysis)

    # Setup Spotify
    st.write("\n🎵 Setting up Spotify connection...")
    sp = setup_spotify_client()
    if not sp:
        st.error("❌ Failed to set up Spotify client.")
        return

    # Search tracks
    st.write("\n🔍 Searching for matching tracks...")
    tracks = search_spotify_tracks(sp, analysis)
    if not tracks:
        st.error("❌ No tracks found.")
        return

    # Display tracks
    display_tracks_details(tracks)

    # Create playlist
    create = st.selectbox("Create Spotify playlist?", ["Yes", "No"])
    if create == "No":
        st.write("\n👋 Thanks for using the Literary Soundtrack Generator!")
        return

    st.write("\n📝 Creating Spotify playlist...")
    playlist_url = create_spotify_playlist(sp, book_info, tracks, analysis)

    if playlist_url:
        st.success(f"🎉 Success! Your literary soundtrack is ready!")
        st.write(f"🔗 Playlist URL: {playlist_url}")
        st.write("\nTip: The playlist is public - you can share it with others!")
    else:
        st.error("\n❌ Failed to create playlist.")

    st.write("\n👋 Thanks for using the Literary Soundtrack Generator!")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        st.write("\n\n👋 Program interrupted. Thanks for using the Literary Soundtrack Generator!")
    except Exception as e:
        st.error(f"\n❌ An unexpected error occurred: {str(e)}")
        st.write("Please try again or contact support if the issue persists.")
