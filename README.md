# Projeto-Beirada

**Equipe:** Computação na Beirada

---

## Sumário

1. [Visão Geral](#visão-geral)
2. [Diagrama de Arquitetura](#diagrama-de-arquitetura)
3. [Componentes da Solução](#componentes-da-solução)
4. [Dependências](#dependências)
5. [Estrutura das Pastas](#estruturas-de-pastas)
6. [Pré-requisitos](#pré-requisitos)
7. [Instruções de Configuração (Setup)](#instruções-de-configuração-setup)

---

## Visão Geral

---

## Diagrama de Arquitetura

---

## Componentes da Solução

### Hardware
| Componente | Função na arquitetura |
|---|---|
| Câmera | Captura das imagens das peças na esteira (entrada do pipeline de visão) |
| Raspberry Pi 5 | Executa a API de inferência (YOLOv8n) e o servidor de streaming |
| Servomotores | Atuação física, desviando cada peça para o caminho correspondente |

### Software
| Camada | Tecnologia | Versão | Função |
|---|---|---|---|
| Modelo de IA | YOLOv8n (Ultralytics) | 8.2.0 | Detecção e classificação das peças em tempo real |
---

## Dependências

---

## Estrutura das Pastas

```
Projeto-Beirada/
├── README.md
├── docker-compose.yml
├── LICENSE
├── .github/
│   └── workflows/
│       └── beirada_deploy.yml       
│
├── beirada_ia/                       
│   ├── Dockerfile.api                
│   ├── Dockerfile.stream             
│   ├── Dockerfile.client             
│   ├── ruff.toml                     
│   │
│   ├── app/
│   │   ├── app.py                    
│   │   ├── model.py                  
│   │   ├── schemas.py                
│   │   ├── core/                     
│   │   ├── services/
│   │   │   ├── capture_image_service.py  
│   │   │   ├── inference_service.py      
│   │   │   ├── log_service.py            
│   │   │   └── serial_service.py         
│   │   ├── preprocessing/
│   │   │   ├── preprocessor.py      
│   │   │   ├── utils/                
│   │   │   └── experiments/          
│   │   ├── static/                  
│   │   └── templates/                
│   │
│   ├── client/
│   │   └── client.py                 
│   │
│   ├── models/
│   │   └── yolov8n.pt.dvc           
│   │
│   ├── scripts/
│   │   ├── deploy.sh                 
│   │   ├── inspect_dataset.py        
│   │   └── validate_model.py         
│   │
│   ├── stream/
│   │   ├── mjpeg_server.py           
│   │   ├── v1_naive.py / v2_threaded.py / v3_optimized.py  
│   │   └── raw_server.py, captire_frames.py
│   │
│   └── tests/
│       ├── test_api.py               
│       └── test_preprocessor.py      
│
└── beirada_esp/                      
    └── ledc_basic/
        ├── README.md                 
        └── main/
            ├── ledc_basic_example_main.c  
            ├── servo.c / servo.h          
            └── filas.c / filas.h          
```

---

## Pré-requisitos

Antes de rodar o projeto, é necessário ter instalado:
- ....
- ....

---

## Instruções de Configuração (Setup)
