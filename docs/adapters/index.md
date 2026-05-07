# Available Adapters

| Adapter | Model | Task types | Domains | Language |
|---------|-------|------------|---------|----------|
| [NER BERT](ner-bert.md) | dslim/bert-base-NER | extract | general, legal | Python |

## Contribute an adapter

1. Install: `pip install synapse-adapter-sdk`
2. Write your adapter following the [first adapter guide](../getting-started/first-adapter.md)
3. Validate: `synapse-validate --adapter your_module.YourAdapter --all-fixtures`
4. Open a PR to [github.com/synapse-ir/adapters](https://github.com/synapse-ir/adapters)

See [BOUNTIES.md](https://github.com/synapse-ir/adapters/blob/main/BOUNTIES.md)
for models where adapters are wanted.
