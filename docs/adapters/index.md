# Available Adapters

| Adapter | Model | Task types | Domains | Language | License |
|---------|-------|------------|---------|----------|---------|
| [NER BERT](ner-bert.md) | dslim/bert-base-NER | extract | general, legal | Python | MIT |
| [OpenAI Classifier](openai-classifier.md) | openai/gpt-4o-mini | classify | general | TypeScript | MIT |
| [JSL Clinical NER](ner-clinical.md) | johnsnowlabs/ner_clinical | extract | medical | Python | MIT (adapter) — requires John Snow Labs license |
| [Docling](docling.md) | docling-project/docling | extract | document, general | Python | MIT |
| [all-MiniLM-L6-v2](all-minilm.md) | sentence-transformers/all-MiniLM-L6-v2 | embed | general | Python | Apache 2.0 |
| [BART Large CNN](bart-large-cnn.md) | facebook/bart-large-cnn | summarize | general | Python | MIT |
| [FinBERT](finbert.md) | ProsusAI/finbert | classify | finance | Python | Apache 2.0 |
| [opus-mt-en-fr](opus-mt-en-fr.md) | Helsinki-NLP/opus-mt-en-fr | translate | multilingual | Python | Apache 2.0 |
| [ms-marco-MiniLM-L6-v2](ms-marco.md) | cross-encoder/ms-marco-MiniLM-L6-v2 | rank | general | Python | Apache 2.0 |
| [twitter-roberta-sentiment](twitter-roberta.md) | cardiffnlp/twitter-roberta-base-sentiment-latest | classify | conversational | Python | CC BY 4.0 |
| [bart-large-mnli](bart-large-mnli.md) | facebook/bart-large-mnli | classify | general | Python | MIT |
| [whisper-large-v3](whisper-large-v3.md) | openai/whisper-large-v3 | transcribe | audio, multilingual | Python | Apache 2.0 |
| [clip-vit-base-patch32](clip-vit-base-patch32.md) | openai/clip-vit-base-patch32 | classify | multimodal, vision | Python | MIT |

## Contribute an adapter

1. Install: `pip install synapse-adapter-sdk`
2. Write your adapter following the [first adapter guide](../getting-started/first-adapter.md)
3. Validate: `synapse-validate --adapter your_module.YourAdapter --all-fixtures`
4. Open a PR to [github.com/synapse-ir/adapters](https://github.com/synapse-ir/adapters)

See [BOUNTIES.md](https://github.com/synapse-ir/adapters/blob/main/BOUNTIES.md)
for models where adapters are wanted.
