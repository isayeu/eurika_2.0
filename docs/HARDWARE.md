# Системные требования (железо)

Ориентиры для **текущего** стека (Ollama / CPU learning) и **будущей** привязки к PyTorch.
Eurika «учится» сейчас через verify → learning KPI / planner (не через градиенты). PyTorch — опциональный слой позже (классификатор интентов, embeddings, эксперименты с дообучением).

**LLM и ML — связка, не замена:** Ollama/OpenAI (слой B) остаётся генератором текста и рассуждений; PyTorch (слой C) — ускорители вокруг него (маршрутизация интентов, embeddings, мелкие классификаторы). ML **не** планируется как замена LLM и не заменяет learning loop Eurika.

---

## 1. Слои нагрузки

| Слой | Что крутится | Нужен ли GPU |
|------|----------------|--------------|
| **A. Core Eurika** | scan / doctor / fix / prove-cycle / learning store | Нет (CPU) |
| **B. Локальный LLM** | Ollama generate (чат, architect) | Желателен; CPU медленно, но возможно |
| **C. PyTorch (ML)** | классификатор / embeddings / лёгкий fine-tune — **рядом с LLM**, не вместо | CPU ок для малых моделей; GPU — для скорости |

---

## 2. Минимальные требования

Достаточно, чтобы **разрабатывать и гонять цикл Eurika**; локальный LLM — опционально и урезанно.

| Ресурс | Минимум | Комментарий |
|--------|---------|-------------|
| **CPU** | 4 ядра x86_64 | scan/verify на средних репо |
| **RAM** | 8 GB | 16 GB комфортнее при Qt + pytest + Ollama |
| **Диск** | 20 GB свободно | venv, модели Ollama (~2–4 GB на 3B), артефакты `.eurika/` |
| **OS** | Linux (основной), macOS/Windows — best effort | Qt: PySide6 |
| **GPU** | Не обязателен | Без GPU: Ollama на CPU или облачный API |
| **VRAM (если GPU)** | ≥ 2 GB | Только лёгкий инференс (`llama3.2:3b` и меньше) |

**Проверенный минимум (инференс, не PyTorch):** NVIDIA GeForce **940MX 4 GB** + драйвер 470 + **Ollama Vulkan** (`OLLAMA_VULKAN=1`, `GGML_VK_VISIBLE_DEVICES` на dGPU). CUDA-пакеты под новый toolkit на таком драйвере могут не работать — см. [TROUBLESHOOTING.md](TROUBLESHOOTING.md) §6.

**Не считается минимумом для PyTorch-LLM:** карты ≤4 GB Maxwell/Pascal без современного CUDA — только инференс через Ollama/Vulkan или CPU.

---

## 3. Оптимальные требования

Комфортная локальная работа: Qt + Ollama 7B-класса + запас под будущий PyTorch.

| Ресурс | Оптимум | Комментарий |
|--------|---------|-------------|
| **CPU** | 8+ ядер | параллельный pytest, несколько циклов |
| **RAM** | 32 GB | Qt + Ollama + IDE + браузер без swap-thrash |
| **Диск** | SSD, ≥ 100 GB свободно | несколько моделей 7B–14B, кэш, датасеты |
| **GPU** | NVIDIA discrete, драйвер с CUDA **12.x** | проще PyTorch wheels и `ollama-cuda` |
| **VRAM** | **12–16 GB** | 7B Q4–Q5 локально; лёгкий fine-tune LoRA 3B–7B |
| **Опционально** | 24 GB+ VRAM | 13B–34B Q4, более серьёзный fine-tune |

**Оптимум «на сейчас» без PyTorch:** 8 GB+ VRAM (например RTX 3060/4060) — спокойно `7B` в Ollama и запас под embeddings.

---

## 4. Будущая привязка к PyTorch (ориентиры)

Цели (см. ROADMAP CR-G3 и опциональные эксперименты): ускорители **поверх** LLM и learning loop, не вместо них.

Типичная связка: direct intents → (опционально) ML-классификатор / embeddings → при необходимости LLM (Ollama/OpenAI) → verify → learn.

| Сценарий | Мин. VRAM | Оптимум VRAM | Примечание |
|----------|-----------|--------------|------------|
| **Классификатор интентов / мелкий MLP** | 2–4 GB или CPU | 4–8 GB | Маленькие тензоры; GPU почти не критичен |
| **Embeddings (sentence-transformers)** | 4 GB | 8 GB | batch на CPU возможен, медленнее |
| **LoRA fine-tune 3B** | 8–12 GB | 16 GB | QLoRA снижает порог; 4 GB — нет |
| **LoRA fine-tune 7B** | 16 GB | 24 GB | На 8–12 GB только очень агрессивный QLoRA |
| **Полный fine-tune / большой pretrain** | вне scope ноутбука | датацентр / облако | Не целевой путь Eurika |

**Политика:** пока железо пользователя < оптимума §3 — PyTorch-фичи остаются **опциональными** (`pip` extra), с CPU-fallback или отключением. Learning KPI / prove-cycle не зависят от torch.

**Шаг 1 (scaffold):** `pip install -e ".[torch]"` (на ≤8 GB / драйвер 470 — CPU wheel). Модуль `eurika.ml.torch_runtime`: probe + CPU matmul smoke; блок `PYTORCH` в `eurika self-check`. Default device — `cpu` (`EURIKA_TORCH_DEVICE`).

**Шаг 2 (paper market):** `eurika ml-market sync|paper|train|status` — свечи spot/USD-M futures → paper labels → tiny Linear на CPU; артефакты в `.eurika/ml/`. Без live-ордеров. Qt **Models → ML** показывает блок прогресса (сделки / accuracy / live / модель).

**Шаг 3 (chat intent router):** `EURIKA_USE_ML_INTENT=1` — tiny Linear поверх exemplars интентов (`eurika.ml.intent_router`); маршрут direct handler / LLM. YAML-интенты всегда первые. Опыт на диске `.eurika/ml/weights/intent_router.pt`.

**RAM 16 GB:** комфортный порог для Qt + Ollama (Vulkan) + paper ML одновременно; классификатор/крупнее локальные модели — реалистичнее, чем на 8 GB.

**Персистентность опыта (обязательно):** перезапуск Qt/Ollama/`eurika` **не** должен сбрасывать накопленный опыт. Learning loop уже пишет в `.eurika/` (events, learning, experience). Будущие ML-артефакты (веса классификатора, калибровка, кэш embeddings) — тоже на диск под `.eurika/ml/` (или аналог), load при старте; в RAM только рабочая копия. Без «обучения с нуля» при каждом запуске.

---

## 5. Быстрая самопроверка

```bash
# CPU / RAM — стандартный Linux
nproc
free -h

# NVIDIA (если есть)
nvidia-smi

# Ollama: в логе serve должно быть library=Vulkan|CUDA и total_vram > 0
# при Vulkan на Optimus: OLLAMA_VULKAN=1 GGML_VK_VISIBLE_DEVICES=<index dGPU>
```

| Наблюдение | Вывод |
|------------|--------|
| Нет GPU / VRAM=0 | Core OK; LLM → CPU или API |
| 4 GB, старый драйвер | Ollama Vulkan + модель ≤3B; PyTorch-LLM — отложить |
| ≥12 GB, CUDA 12 | Готовность к опциональному PyTorch extra |

---

## Ссылки

- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) §6 — Ollama GPU
- [UI.md](UI.md) — Models tab (CUDA / Vulkan)
- [ONBOARDING.md](ONBOARDING.md) — быстрый старт
- [ROADMAP.md](ROADMAP.md) §5.4 CR-G3 — PyTorch-классификатор (опционально)
- [MEMORY.md](MEMORY.md) — learning loop (без PyTorch)
