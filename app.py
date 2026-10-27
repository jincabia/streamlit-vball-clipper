import streamlit as st
import json
import os
import time
import subprocess
from pathlib import Path

SAVE_FILE = "timestamps.json"

# --- HELPER FUNCTIONS ---
def load_timestamps():
    try:
        with open(SAVE_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_timestamps(data):
    temp = SAVE_FILE + ".tmp"
    with open(temp, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(temp, SAVE_FILE)

def fmt(seconds):
    return time.strftime("%H:%M:%S", time.gmtime(max(0, seconds)))

def clip_highlight(original_video, event_time, output_filename, padding=10):
    start_time = max(0, event_time - padding)
    clip_duration = padding * 2
    cmd = [
        'ffmpeg', '-y',
        '-ss', str(start_time),
        '-i', original_video,
        '-t', str(clip_duration),
        '-c', 'copy',
        output_filename
    ]
    subprocess.run(cmd, check=True)

def combine_clips(clip_filenames, final_output):
    concat_file = 'concat_list.txt'
    with open(concat_file, 'w', encoding='utf-8') as f:
        for clip in clip_filenames:
            safe = os.path.abspath(clip).replace("'", r"'\''")
            f.write(f"file '{safe}'\n")
    cmd = [
        'ffmpeg', '-y',
        '-f', 'concat',
        '-safe', '0',
        '-i', concat_file,
        '-c', 'copy',
        final_output
    ]
    subprocess.run(cmd, check=True)
    if os.path.exists(concat_file):
        os.remove(concat_file)

# --- STREAMLIT UI CONFIG ---
st.set_page_config(page_title="Clip Player & Tracker", layout="wide")

st.title("Web Clip Player & FFmpeg Tracker")

# Sidebar for Video Management
st.sidebar.header("1. Select or Upload Video")
uploaded_file = st.sidebar.file_uploader("Upload an MP4 video", type=["mp4"])

video_path = None
if uploaded_file is not None:
    # Save uploaded file locally so FFmpeg and player can access it
    os.makedirs("uploads", exist_ok=True)
    video_path = os.path.join("uploads", uploaded_file.name)
    with open(video_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    st.sidebar.success(f"Loaded: {uploaded_file.name}")
else:
    # Fallback to local files if any exist
    local_videos = [str(p) for p in Path(".").glob("*.mp4")] + [str(p) for p in Path("uploads").glob("*.mp4")] if os.path.exists("uploads") else []
    if local_videos:
        video_path = st.sidebar.selectbox("Or choose from local server files:", local_videos)

# Tabs for workflow separation
tab_player, tab_exporter = st.tabs(["Player & Logger", "Export & Compile Clips"])

# --- TAB 1: PLAYER & TIMESTAMP LOGGER ---
with tab_player:
    if video_path:
        st.subheader(f"Now Playing: {Path(video_path).name}")
        
        # We use HTML5 video element with custom event listener for hotkeys ('s' to save timestamp)
        video_bytes = open(video_path, "rb").read()
        st.video(video_path)

        col1, col2 = st.columns(2)
        with col1:
            manual_time = st.number_input("Or input timestamp manually (seconds):", min_value=0.0, step=0.5, format="%.2f")
            if st.button("Save Manual Timestamp"):
                data = load_timestamps()
                data.setdefault(video_path, []).append(round(manual_time, 2))
                # Sort and remove duplicates
                data[video_path] = sorted(list(set(data[video_path])))
                save_timestamps(data)
                st.success(f"Saved timestamp at {fmt(manual_time)}!")

        # Display currently saved timestamps for this video
        st.markdown("---")
        st.subheader("Saved Timestamps for this Video")
        all_data = load_timestamps()
        current_stamps = all_data.get(video_path, [])
        
        if current_stamps:
            for idx, ts in enumerate(current_stamps):
                c1, c2, c3 = st.columns([2, 2, 1])
                c1.write(f"Timestamp {idx+1}: **{fmt(ts)}** ({ts}s)")
                if c2.button("Delete", key=f"del_{video_path}_{idx}"):
                    current_stamps.remove(ts)
                    all_data[video_path] = current_stamps
                    save_timestamps(all_data)
                    st.rerun()
        else:
            info_msg = "No timestamps saved for this video yet."
            st.info(info_msg)
    else:
        st.warning("Please upload or select an MP4 video file from the sidebar to begin.")

# --- TAB 2: EXPORT & COMPILE CLIPS ---
with tab_exporter:
    st.subheader("FFmpeg Clip Extractor & Merger")
    st.write("Process all saved timestamps from `timestamps.json` into individual clips and combine them into a highlight reel.")

    padding = st.slider("Clip Padding (seconds before/after timestamp):", min_value=1, max_value=30, value=10)
    
    if st.button("Generate Highlight Reel"):
        data = load_timestamps()
        if not data:
            st.error("No timestamps found in `timestamps.json`!")
        else:
            os.makedirs("clips", exist_ok=True)
            saved_clips = []
            
            progress_bar = st.progress(0)
            total_items = sum(len(stamps) for stamps in data.values())
            current_item = 0

            try:
                for path, timestamps in data.items():
                    if not os.path.exists(path):
                        st.warning(f"Video file not found locally: {path}. Skipping.")
                        continue
                    
                    formatted_path = Path(path).stem.replace(" ", "_")
                    
                    for event_time in timestamps:
                        clip_name = f"clips/{formatted_path}-clip_{event_time}s.mp4"
                        clip_highlight(path, event_time, output_filename=clip_name, padding=padding)
                        saved_clips.append(clip_name)
                        
                        current_item += 1
                        progress_bar.progress(current_item / total_items)

                if saved_clips:
                    final_output_file = "final_highlight_reel.mp4"
                    combine_clips(saved_clips, final_output_file)
                    st.success("Successfully generated highlight reel!")
                    
                    # Provide download button for final video
                    with open(final_output_file, "rb") as f:
                        st.download_button(
                            label="Download Final Highlight Reel",
                            data=f,
                            file_name="highlight_reel.mp4",
                            mime="video/mp4"
                        )
                else:
                    st.warning("No clips were generated.")
            except Exception as e:
                st.error(f"An error occurred during FFmpeg processing: {e}")