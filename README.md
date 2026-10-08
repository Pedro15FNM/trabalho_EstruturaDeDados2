# Skyline Skip List

Nosso projeto é um jogo de plataforma 2D com visão lateral, no qual o mapa representa visualmente uma Skip List. Cada nó da estrutura é ilustrado como um prédio vertical, onde a quantidade de níveis do nó determina o número de andares do edifício. O jogador se movimenta entre os prédios utilizando tirolesas, que representam graficamente os ponteiros da Skip List.

A base de dados, contendo os animais e suas categorias, é gerenciada por uma Árvore de Afunilamento (Splay Tree), que possui um nó para cada animal. Já a Skip List possui um nó referente a cada classe taxonômica presente na base (ou seja, cada prédio representa uma classe distinta).

No início de cada rodada, um animal é sorteado da Árvore de Afunilamento e suas informações são exibidas. O objetivo do jogador é alcançar o prédio referente à classe desse animal navegando pelas tirolesas (começando pela cabeça da lista), com cuidado para não esgotar a energia de movimentação(tem uma quantidade limitada de movimentos por rodada, se gastar toda a energia perde a rodada), e com cuidado para não ultrapassar o prédio da classse alvo(se ultrapassar perde o jogo). Ao alcançar o objetivo, um novo animal de outra classe é sorteado e o ciclo se repete, iniciando uma nova rodada.

### Processo de desenvolvimento

O desenvolvimento iniciou com a ideação do jogo logo após a apresentação da proposta do projeto. Em seguida, focamos no polimento da ideia, com debates sobre as características da aplicação, definição do escopo e criação dos primeiros diagramas e documentos de conceito.

Muitas ideias iniciais evoluíram. A escolha da base de dados, por exemplo, foi um desafio. Como queríamos integrar uma mecânica de combate, buscamos inicialmente bases contendo monstros de RPG (como _Dungeons & Dragons_), mas nenhuma possuía o volume de dados necessário. A própria mecânica de combate, que originalmente seguiria um estilo "RPG de turnos" sempre que o jogador alcançasse o nó objetivo, foi simplificada para uma resolução rápida via "cara ou coroa" (50/50).

Tecnicamente, a intenção inicial era desenvolver o jogo na engine Unity. Contudo, percebemos rapidamente que a ferramenta era superdimensionada para o escopo do nosso MVP. Optamos então por utilizar a linguagem Python em conjunto com a biblioteca Pygame.

Além do Pygame, a aplicação se apoiou em bibliotecas nativas do Python: `csv` para leitura dos dados, `pickle` para persistência em cache, `unittest` para garantia de qualidade e `hashlib`/`os`/`pathlib` para o gerenciamento e validação de arquivos. O projeto foi construído de maneira incremental: primeiro validamos os dados básicos e as estruturas (Splay Tree e Skip List) de forma isolada, para então integrá-las ao motor do jogo e à interface gráfica, passando por rodadas contínuas de testes e refatorações até chegarmos à versão final. 

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
