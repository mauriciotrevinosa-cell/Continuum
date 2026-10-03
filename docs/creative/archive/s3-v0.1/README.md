# Archived — Season 3 LN production v0.1

These are the 155 v0.1 Season 3 chapters and their eight volume indexes
(volumes 10–17), kept for reference after the v0.2 rebuild replaced them.

They are **archived, not deleted**. Their creative history is in Git.

They live in this subdirectory for a mechanical reason: the project scans its
documents with a non-recursive glob, and a convention gives a chapter the id
`<episode>-ln-chapter-NN` with no version in it. While both versions sat in
`docs/creative/`, the two files collided on that id and the first one scanned
won — always `_v0.1.md`, because it sorts before `_v0.2.md`. The rebuilt season
existed on disk and could not be read. Moving these out of the scanned
directory lets the v0.2 documents take their own ids.

To bring any of this back into production, move the file back up to
`docs/creative/` and remove the SUPERSEDED line from its `**Status:**`.
