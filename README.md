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

O Projeto Beirada é uma solução embarcada para identificação e triagem automática de componentes em uma linha de produção. Uma câmera captura continuamente as peças em movimento, uma API de inferência (YOLOv8n) as classifica em tempo real, e o resultado é transmitido a um microcontrolador ESP32-S3, responsável por acionar o servomotor correto no momento exato

---

## Diagrama de Arquitetura

(INSIRA DIAGRAMA)

---

## Componentes da Solução

### Hardware
| Componente | Função na arquitetura |
|---|---|
| Câmera | Captura das imagens das peças na esteira (entrada do pipeline de visão) |
| Raspberry Pi 5 | Executa a API de inferência (YOLOv8n) e o servidor de streaming |
| ESP32-S3 | Recebe a classe detectada via serial e controla os servomotores |
| Servomotores | Atuação física, desviando cada peça para o caminho correspondente |

### Software
| Camada | Tecnologia | Versão | Função |
|---|---|---|---|
| Modelo de IA | YOLOv8n (Ultralytics) | 8.2.0 | Detecção e classificação das peças em tempo real |
| API de inferência |  |  |  |
| Streaming |  |  |  |
| Pré-processamento |  |  |  |
| Comunicação IoT |  |  |  |
| Firmware embarcado |  |  |  |
| Versionamento de modelo |  |  |  |
| Orquestração |  |  |  |
---

## Dependências

### Python - API e Streaming
```
fastapi==0.111.0
uvicorn[standard]==0.29.0
ultralytics==8.2.0
Pillow==11.0.0
numpy==1.26.4
httpx==0.27.0
opencv-python-headless==4.9.0.80
flask==3.1.3
pyserial==3.5.0
```

### Python - Cliente de teste
```
httpx==0.27.0
Pillow==10.3.0
```

### Firmware - ESP32-S3

### Plataformas e ferramentas externas
  
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

...
