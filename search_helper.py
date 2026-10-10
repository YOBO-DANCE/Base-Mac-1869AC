# Remember always give the list in this way
"""
[
    (index, "song_name1"),
    (index, "song_name2"),
    (index, "song_name3")...
]
"""

def search_help(query: str, songs_list):
    q = query.strip().lower()

    # Suppose some idiot tried to enter just spaces, my code will slap them with a full list of songs LOL
    if not q:
        return songs_list

    filtered_list = [(i, name) for i, name in songs_list if q in name.lower()]
    # clean_list = [f"{i}, {name}" for i, name in filtered_list]

    return filtered_list
    

# if __name__ == "__main__":
#     mock_songs = [
#         (0, "Babydoll"),
#         (1, "Hozier"),
#         (2, "Love Me"),
#         (3, "Summer Lovin'"),
#         (4, "Nightcall")
#     ]
#     print(search_help(input(), mock_songs))


# psst...Testing
if __name__ == "__main__":
    mock_songs = [
        (0, "Babydoll"),
        (1, "Hozier"),
        (2, "Love Me"),
        (3, "Summer Lovin'"),
        (4, "Nightcall")
    ]

    results = search_help(input("Write the song name and press enter: "), mock_songs)
    if not results:
            print("No results found!")
    else:
        print(f"Results({len(results)}):")
        print(*results, sep="\n")