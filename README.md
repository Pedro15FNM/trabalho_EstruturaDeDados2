# Skyline Skip List

Jogo 2D em Pygame no qual os prédios representam classes taxonômicas de uma Skip List. Navegue pelas tirolesas até a classe do animal-alvo, administrando energia e evitando ultrapassagens. Ao chegar, um painel apresenta o animal e aguarda ENTER ou ESPAÇO para resolver o combate 50/50.

## Executar

Requer Python 3.10 ou superior. Instale a única dependência externa:

```sh
python -m pip install -r requirements.txt
```

Execute a partir da raiz do projeto:

```sh
python main.py
```

O modo de desenvolvimento usa dados fictícios e não precisa dos CSVs:

```sh
python main.py --fake 100
```

Para o dataset real, coloque `taxa.csv` em `data/` junto de `VernacularNames-portuguese.csv`. O arquivo de taxa é grande e pode ser obtido pelo link de distribuição do projeto: https://drive.google.com/drive/folders/1xJbYSYOvWb6_E_x2WlgvXXpkQzw0AI4J?usp=drive_link. A primeira construção da Splay Tree pode levar algum tempo; depois ela é reutilizada pelo cache pickle.

## Imagens iNaturalist

Ao sortear um animal, o jogo usa `taxonID` ou `identifier` para extrair o ID do iNaturalist. O ID interno usado pela Splay Tree permanece independente. Somente o táxon atual é consultado em `https://api.inaturalist.org/v1/taxa/{id}`; a leitura em lote do CSV não faz chamadas de rede.

A consulta e o download acontecem em uma thread de fundo. A foto prioriza `medium_url`, seguindo para `square_url` e `url` quando necessário. Arquivos e metadados ficam em `data/animal_images/{id}.jpg` e `data/animal_images/{id}.json`. O cache não é distribuído como asset do jogo. Para apagá-lo no Linux/macOS:

```sh
rm -rf data/animal_images
```

Sem internet, sem foto ou diante de erro de API, o jogo continua e mostra “Imagem não disponível”. A imagem é apresentada com proporção preservada. Quando há foto, o painel mostra atribuição, código de licença quando informado e URL do táxon. O iNaturalist pode fornecer imagens com licenças diferentes ou sem licença declarada; não presuma permissão de redistribuição. Verifique os termos da foto e mantenha os créditos e a licença correspondentes ao reutilizá-la. A origem dos dados taxonômicos e da API é o iNaturalist.

## Testes

```sh
python -m unittest discover -s tests -v
python -m compileall .
```
