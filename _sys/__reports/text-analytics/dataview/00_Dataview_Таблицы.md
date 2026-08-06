# Dataview Tables

## Summary by chapter (22 rows)

```dataview
TABLE files_count as Files, words as Words, symbols as Symbols, words_leng as WordsLeng, sentences as Sentences, wateriness as Wateriness, nausea as Nausea, lexicon_size as LexiconSize, lexical_richness as LexRich, top_words_3 as Top3Words
FROM #chapter-metric
WHERE contains(file.path, "_sys/__reports/text-analytics/dataview/chapters") AND dv_ready
SORT chapter ASC
```

## Top scenes by sentence length

```dataview
TABLE file.link as File, chapter, scene, words, sentences, avg_sentence_len, dialogue_share
FROM #text-metric
WHERE contains(file.path, "_sys/__reports/text-analytics/dataview/files") AND dv_ready
SORT avg_sentence_len DESC
LIMIT 30
```

## Dialogue-heavy scenes

```dataview
TABLE file.link as File, chapter, scene, dialogue_share, words
FROM #text-metric
WHERE contains(file.path, "_sys/__reports/text-analytics/dataview/files") AND dv_ready AND dialogue_share >= 35
SORT dialogue_share DESC
LIMIT 30
```

## Chapter 7 details

```dataview
TABLE file.link as File, scene, words, avg_sentence_len, dialogue_share
FROM #text-metric
WHERE contains(file.path, "_sys/__reports/text-analytics/dataview/files") AND dv_ready AND chapter = 7
SORT words DESC
```
