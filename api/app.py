import asyncio
import aiohttp
from flask import Flask, render_template, request

app = Flask(__name__)

# Função assíncrona para buscar dados de uma URL
async def fetch(session, url):
    async with session.get(url) as response:
        return await response.json()

# Função para buscar dados dos Pokémon de forma paralela
async def get_pokemon_data(name=None, pokemon_type=None, habitat=None, offset=0, limit=10):
    async with aiohttp.ClientSession() as session:
        # Função auxiliar para buscar e adicionar o habitat aos Pokémon
        async def add_habitat(pokemon):
            try:
                species_url = f"https://pokeapi.co/api/v2/pokemon-species/{pokemon['id']}"
                species_data = await fetch(session, species_url)
                if species_data and "habitat" in species_data:
                    pokemon["habitat"] = species_data["habitat"].get("name", "Desconhecido")
                else:
                    pokemon["habitat"] = "Desconhecido"
            except Exception as e:
                print(f"Erro ao buscar habitat: {e}")
                pokemon["habitat"] = "Desconhecido"

        # Se o nome é fornecido, busca diretamente o Pokémon pelo nome
        if name:
            url = f"https://pokeapi.co/api/v2/pokemon/{name.lower()}"
            try:
                pokemon_data = await fetch(session, url)
                await add_habitat(pokemon_data)
                return [pokemon_data]
            except Exception as e:
                print(f"Erro ao buscar Pokémon: {e}")
                return []

        # Se ambos tipo e habitat forem fornecidos, aplica a interseção
        if pokemon_type and habitat:
            type_url = f"https://pokeapi.co/api/v2/type/{pokemon_type}"
            habitat_url = f"https://pokeapi.co/api/v2/pokemon-habitat/{habitat}"

            try:
                type_data = await fetch(session, type_url)
                habitat_data = await fetch(session, habitat_url)

                type_pokemon_names = {p["pokemon"]["name"] for p in type_data["pokemon"]}
                habitat_pokemon_names = {p["name"] for p in habitat_data["pokemon_species"]}

                # Interseção e aplicação do offset e limit
                common_pokemon_names = list(type_pokemon_names & habitat_pokemon_names)[offset:offset + limit]
                tasks = [fetch(session, f"https://pokeapi.co/api/v2/pokemon/{name}") for name in common_pokemon_names]
                pokemon_details = await asyncio.gather(*tasks)

                # Adiciona habitat a cada Pokémon
                await asyncio.gather(*(add_habitat(p) for p in pokemon_details))
                return pokemon_details

            except Exception as e:
                print(f"Erro ao buscar tipo e habitat: {e}")
                return []

        # Se apenas tipo for fornecido
        if pokemon_type:
            try:
                type_url = f"https://pokeapi.co/api/v2/type/{pokemon_type}"
                type_data = await fetch(session, type_url)
                pokemon_urls = [p["pokemon"]["url"] for p in type_data["pokemon"][offset:offset + limit]]

                tasks = [fetch(session, url) for url in pokemon_urls]
                pokemon_details = await asyncio.gather(*tasks)

                await asyncio.gather(*(add_habitat(p) for p in pokemon_details))
                return pokemon_details

            except Exception as e:
                print(f"Erro ao buscar Pokémon por tipo: {e}")
                return []

        # Se apenas habitat for fornecido
        if habitat:
            try:
                habitat_url = f"https://pokeapi.co/api/v2/pokemon-habitat/{habitat}"
                habitat_data = await fetch(session, habitat_url)
                pokemon_names = [p["name"] for p in habitat_data["pokemon_species"][offset:offset + limit]]

                tasks = [fetch(session, f"https://pokeapi.co/api/v2/pokemon/{name}") for name in pokemon_names]
                pokemon_details = await asyncio.gather(*tasks)

                await asyncio.gather(*(add_habitat(p) for p in pokemon_details))
                return pokemon_details

            except Exception as e:
                print(f"Erro ao buscar Pokémon por habitat: {e}")
                return []

        # Busca padrão sem filtros
        try:
            url = f"https://pokeapi.co/api/v2/pokemon?offset={offset}&limit={limit}"
            pokemons = await fetch(session, url)
            tasks = [fetch(session, result["url"]) for result in pokemons["results"]]
            pokemon_details = await asyncio.gather(*tasks)

            await asyncio.gather(*(add_habitat(p) for p in pokemon_details))
            return pokemon_details

        except Exception as e:
            print(f"Erro ao buscar Pokémon sem filtros: {e}")
            return []

      


# Função para buscar tipos de Pokémon
async def get_types():
    url = "https://pokeapi.co/api/v2/type"
    async with aiohttp.ClientSession() as session:
        data = await fetch(session, url)
        return [t["name"] for t in data["results"]]

# Função para buscar habitats de Pokémon
async def get_habitats():
    url = "https://pokeapi.co/api/v2/pokemon-habitat"
    async with aiohttp.ClientSession() as session:
        data = await fetch(session, url)
        return [h["name"] for h in data["results"]]

# Modificando a rota principal para incluir tipos e habitats
@app.route('/', methods=['GET'])
async def index():
    page = int(request.args.get('page', 1))
    limit = 10
    offset = (page - 1) * limit

    # Recebe os filtros da URL
    name = request.args.get('name')
    pokemon_type = request.args.get('type')
    habitat = request.args.get('habitat')

    # Busca dados dos Pokémon com os filtros e offset aplicados
    pokemons_data = await get_pokemon_data(name, pokemon_type, habitat, offset, limit)

    # Formata os dados para renderização
    pokemons = [
        {
            "id": pokemon["id"],
            "name": pokemon["name"],
            "image": pokemon["sprites"]["front_default"],
            "types": [t["type"]["name"] for t in pokemon["types"]],
            "habitat": pokemon.get("habitat", "Desconhecido"),
            "url": f"/pokemon/{pokemon['id']}"
        }
        for pokemon in pokemons_data
    ]

    # Busca tipos e habitats da API para preencher os selects
    types = await get_types()
    habitats = await get_habitats()

    return render_template('index.html', pokemons=pokemons, page=page, types=types, habitats=habitats)




# Rota para detalhes de um Pokémon específico
@app.route('/pokemon/<int:pokemon_id>')
async def pokemon_detail(pokemon_id):
    async with aiohttp.ClientSession() as session:
        pokemon_url = f"https://pokeapi.co/api/v2/pokemon/{pokemon_id}"
        habitat_url = f"https://pokeapi.co/api/v2/pokemon-species/{pokemon_id}"

        pokemon_data = await fetch(session, pokemon_url)
        habitat_data = await fetch(session, habitat_url)

        pokemon = {
            "name": pokemon_data["name"],
            "image": pokemon_data["sprites"]["other"]["official-artwork"]["front_default"],
            "height": pokemon_data["height"] / 10,
            "weight": pokemon_data["weight"] / 10,
            "types": [t["type"]["name"] for t in pokemon_data["types"]],
            "habitat": habitat_data.get("habitat", {}).get("name", "Desconhecido")
        }

    return render_template('pokemon_detail.html', pokemon=pokemon)

if __name__ == '__main__':
    app.run(debug=True)
