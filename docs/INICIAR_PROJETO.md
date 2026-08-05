# 🚀 Como Iniciar o PokeAI Blue

> Guia para rodar a IA jogando Pokémon Blue

---

## 📋 Pré-requisitos

1. **Python 3.8+** instalado.
2. **ROM do Pokémon Blue** (`Pokemon Blue.gb`) - **Você deve providenciar este arquivo legalmente.**

---

## 🛠️ Instalação

1. **Coloque a ROM na pasta correta:**
   - Copie seu arquivo `Pokemon Blue.gb` para a pasta `roms/` dentro deste projeto.
   - O caminho final deve ser: `roms/Pokemon Blue.gb`

2. **Crie um ambiente virtual (opcional mas recomendado):**
   ```bash
   python -m venv venv
   source venv/bin/activate  # Linux/Mac
   # ou
   venv\Scripts\activate     # Windows
   ```

3. **Instale as dependências:**
   ```bash
   pip install -r requirements.txt
   ```

---

## 🎮 Como Rodar

### Modo Visual (Padrão)
Para ver a IA jogando em tempo real:

```bash
python src/main.py
```

### Modo Headless (Sem Janela)
Para treinar ou rodar em background (mais rápido):

```bash
python src/main.py --headless
```

### Opções Adicionais
- `--rom "caminho/para/rom.gb"`: Especificar outro caminho de ROM.
- `--frames 1000`: Rodar apenas por um número específico de frames.

---

## 🤖 O que a IA faz agora?

Atualmente, a IA é um **Agente Aleatório**. Ela:
1. Inicia o emulador.
2. Pressiona botões aleatoriamente.
3. Não tem objetivo definido (ainda).

Nos próximos passos, implementaremos:
- [ ] Leitura de memória (HP, Party, Location).
- [ ] Navegação básica.
- [ ] Batalhas inteligentes.
