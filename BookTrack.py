import streamlit as st
import requests
import google.generativeai as genai
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import os

# Set page configuration
st.set_page_config(
    page_title="Literary Soundtrack Generator",
    page_icon="📚",
    layout="wide"
)

# Add custom CSS for better styling
st.markdown("""
<style>
    .main {
        padding: 2rem;
    }
    .stButton button {
        background-color: #1DB954;
        color: white;
        border-radius: 30px;
        padding: 0.5rem 2rem;
        font-weight: bold;
    }
    .book-cover {
        border-radius: 10px;
        box-shadow: 0 4px 8px rgba(0,0,0,0.2);
    }
    h1, h2, h3 {
        color: #1DB954;
    }
    .stAlert {
        border-radius: 10px;
    }
    .track-card {
        background-color: #f9f9f9;
        border-radius: 10px;
        padding: 1rem;
        margin-bottom: 1rem;
        border-left: 5px solid #1DB954;
    }
</style>
""", unsafe_allow_html=True)

# Initialize session state for storing results
if 'book_info' not in st.session_state:
    st.session_state.book_info = None
if 'analysis' not in st.session_state:
    st.session_state.analysis = None
if 'tracks' not in st.session_state:
    st.session_state.tracks = None

# API Configuration
@st.cache_resource
def load_api_keys():
    """Load API keys from Streamlit secrets"""
    try:
        return {
            "GOOGLE_BOOKS_API_KEY": st.secrets["GOOGLE_BOOKS_API_KEY"],
            "GEMINI_API_KEY": st.secrets["GEMINI_API_KEY"],
            "SPOTIFY_CLIENT_ID": st.secrets["SPOTIFY_CLIENT_ID"],
            "SPOTIFY_CLIENT_SECRET": st.secrets["SPOTIFY_CLIENT_SECRET"]
        }
    except Exception as e:
        st.error(f"Error loading API keys: {e}")
        st.info("Please ensure you've configured your API keys in Streamlit's secrets management.")
        return None

def get_book_info(title, author):
    """Fetch book information from Google Books API"""
    keys = load_api_keys()
    if not keys:
        return None
    
    query = f"intitle:{title}+inauthor:{author}"
    url = f"https://www.googleapis.com/books/v1/volumes?q={query}&key={keys['GOOGLE_BOOKS_API_KEY']}"

    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()

        if "items" not in data or not data["items"]:
            return None

        book = data["items"][0]["volumeInfo"]
        return {
            "title": book.get("title", "Unknown Title"),
            "authors": book.get("authors", ["Unknown Author"]),
            "summary": book.get("description", "No description available."),
            "thumbnail": book.get("imageLinks", {}).get("thumbnail", "")
        }

    except Exception as e:
        st.error(f"Error fetching book info: {e}")
        return None

def analyze_book_with_gemini(book_info):
    """Analyze book content using Google's Gemini AI"""
    keys = load_api_keys()
    if not keys:
        return None
    
    try:
        genai.configure(api_key=keys["GEMINI_API_KEY"])
        model = genai.GenerativeModel('gemini-2.0-flash')
        
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
        Time Period/Cultural Context: [comma-separated list]
        Keywords: [comma-separated list]
        """

        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        st.error(f"Error with Gemini API: {e}")
        return None

def parse_gemini_analysis(analysis_text):
    """Parse the structured response from Gemini into a dictionary"""
    if not analysis_text:
        return None

    try:
        sections = {}
        current_section = None
        
        for line in analysis_text.split('\n'):
            line = line.strip()
            if not line:
                continue
                
            if ':' in line:
                section_name, content = line.split(':', 1)
                section_name = section_name.strip()
                content = content.strip()
                
                if content.startswith('[') and content.endswith(']'):
                    content = content[1:-1]
                
                sections[section_name] = [item.strip() for item in content.split(',')]
                current_section = section_name
            elif current_section:
                # Handle multi-line content
                additional_content = line.strip()
                if additional_content:
                    if isinstance(sections[current_section], list):
                        sections[current_section].extend([item.strip() for item in additional_content.split(',')])
                    else:
                        sections[current_section] += " " + additional_content

        return sections
    except Exception as e:
        st.error(f"Error parsing Gemini analysis: {e}")
        return None

def setup_spotify_client():
    """Set up Spotify client using Client Credentials (no login required)"""
    keys = load_api_keys()
    if not keys:
        return None
    
    try:
        auth_manager = SpotifyClientCredentials(
            client_id=keys["SPOTIFY_CLIENT_ID"],
            client_secret=keys["SPOTIFY_CLIENT_SECRET"]
        )
        return spotipy.Spotify(auth_manager=auth_manager)
    except Exception as e:
        st.error(f"Error in Spotify authentication: {e}")
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
        for tone in analysis['Emotional Tones'][:2]:  # Limit to avoid too many queries
            for genre in analysis['Genres'][:2]:
                search_queries.append({
                    'terms': f'{tone} {genre}',
                    'limit': int(max_tracks * search_weights['Emotional Tones'])
                })

    # Mood queries
    if 'Moods' in analysis:
        for mood in analysis['Moods'][:3]:  # Limit to avoid too many queries
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
                # Add preview URL and album image
                preview_url = item.get("preview_url", "")
                album_image = item["album"]["images"][1]["url"] if item["album"]["images"] else ""
                
                track = {
                    "id": item["id"],
                    "name": item["name"],
                    "artist": item["artists"][0]["name"],
                    "album": item["album"]["name"],
                    "uri": item["uri"],
                    "popularity": item["popularity"],
                    "preview_url": preview_url,
                    "album_image": album_image
                }
                
                # Check if track is already in the list
                if not any(t["id"] == track["id"] for t in tracks):
                    tracks.append(track)

        except Exception as e:
            st.warning(f"Error searching for '{query['terms']}': {e}")
            continue

    # Sort by popularity and return top tracks
    tracks.sort(key=lambda x: x['popularity'], reverse=True)
    return tracks[:max_tracks]

def display_book_info(book_info):
    """Display book information with improved formatting"""
    col1, col2 = st.columns([1, 3])
    
    with col1:
        if book_info.get('thumbnail'):
            st.image(book_info['thumbnail'], width=200, caption="Book Cover", use_column_width=True)
        else:
            st.image("https://via.placeholder.com/150x200?text=No+Cover", width=150)
    
    with col2:
        st.markdown(f"## {book_info['title']}")
        st.markdown(f"**Author(s):** {', '.join(book_info['authors'])}")
        
        if book_info.get('summary'):
            with st.expander("Summary", expanded=True):
                st.write(book_info['summary'])

def display_analysis_results(analysis):
    """Display analysis results in a structured format"""
    st.subheader("📊 Book Analysis Results")
    
    sections = {
        'Emotional Tones': '🎭 Emotional Tones',
        'Genres': '🎵 Musical Genres',
        'Moods': '🌈 Moods',
        'Time Period/Cultural Context': '📅 Time Period/Cultural Context',
        'Keywords': '🔑 Keywords'
    }

    cols = st.columns(len(sections))
    
    for i, (section, header) in enumerate(sections.items()):
        with cols[i]:
            st.markdown(f"##### {header}")
            if section in analysis:
                for item in analysis[section]:
                    st.markdown(f"• {item}")

def display_tracks_details(tracks):
    """Display track information in a formatted, visual way"""
    st.subheader("🎵 Recommended Soundtrack")
    
    # Display tracks in a grid
    cols_per_row = 3
    for i in range(0, len(tracks), cols_per_row):
        cols = st.columns(cols_per_row)
        for j in range(cols_per_row):
            if i + j < len(tracks):
                track = tracks[i + j]
                with cols[j]:
                    st.markdown(f"""
                    <div class="track-card">
                        <h4>{track['name']}</h4>
                        <p><strong>Artist:</strong> {track['artist']}</p>
                        <p><strong>Album:</strong> {track['album']}</p>
                        <p><strong>Popularity:</strong> {"⭐" * ((track['popularity'] // 20) + 1)} ({track['popularity']}/100)</p>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    # Display album cover
                    if track['album_image']:
                        st.image(track['album_image'], width=150)
                        
                    # Add Spotify play button
                    st.markdown(f"[Listen on Spotify](https://open.spotify.com/track/{track['id']})")
                    
                    # Add preview if available
                    if track['preview_url']:
                        st.audio(track['preview_url'])

def main():
    """Main application flow"""
    st.title("📚 Literary Soundtrack Generator 🎵")
    st.markdown("Generate a personalized soundtrack for your favorite books")
    
    with st.form("book_form"):
        col1, col2 = st.columns(2)
        with col1:
            book_title = st.text_input("Book Title:", placeholder="e.g., Pride and Prejudice")
        with col2:
            book_author = st.text_input("Author:", placeholder="e.g., Jane Austen")
        
        submit_button = st.form_submit_button("Generate Soundtrack")
    
    if submit_button and book_title and book_author:
        # Create a progress indicator
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        # Step 1: Fetch book information
        status_text.text("📖 Fetching book details...")
        progress_bar.progress(10)
        book_info = get_book_info(book_title, book_author)
        
        if not book_info:
            st.error("❌ Could not find this book. Please check the title and author spelling.")
            return
        
        # Store book info in session state
        st.session_state.book_info = book_info
        progress_bar.progress(30)
        
        # Step 2: Analyze book content
        status_text.text("🤖 Analyzing book content...")
        analysis_text = analyze_book_with_gemini(book_info)
        
        if not analysis_text:
            st.error("❌ Failed to analyze the book content.")
            return
        
        analysis = parse_gemini_analysis(analysis_text)
        if not analysis:
            st.error("❌ Could not parse the analysis results.")
            return
        
        # Store analysis in session state
        st.session_state.analysis = analysis
        progress_bar.progress(60)
        
        # Step 3: Get music recommendations
        status_text.text("🎵 Finding matching tracks...")
        sp = setup_spotify_client()
        if not sp:
            st.error("❌ Could not connect to Spotify. Please check your API credentials.")
            return
            
        tracks = search_spotify_tracks(sp, analysis)
        if not tracks:
            st.error("❌ No matching tracks found.")
            return
            
        # Store tracks in session state
        st.session_state.tracks = tracks
        progress_bar.progress(100)
        status_text.text("✅ Your literary soundtrack is ready!")
        
        # Force a rerun to display results
        st.experimental_rerun()
    
    # Display results if available
    if st.session_state.book_info and st.session_state.analysis and st.session_state.tracks:
        st.markdown("---")
        display_book_info(st.session_state.book_info)
        st.markdown("---")
        display_analysis_results(st.session_state.analysis)
        st.markdown("---")
        display_tracks_details(st.session_state.tracks)
        
        # Add option to start over
        if st.button("Create Another Soundtrack"):
            st.session_state.book_info = None
            st.session_state.analysis = None
            st.session_state.tracks = None
            st.experimental_rerun()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        st.write("👋 Thanks for using the Literary Soundtrack Generator!")
    except Exception as e:
        st.error(f"❌ An unexpected error occurred: {str(e)}")
        st.info("Please check your API credentials and try again.")
