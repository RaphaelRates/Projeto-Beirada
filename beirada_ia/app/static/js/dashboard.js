(function() {
    'use strict';

    // DOM
    const periodSelect = document.getElementById('periodSelect');
    const refreshBtn = document.getElementById('refreshBtn');
    const totalEl = document.getElementById('totalPredictions');
    const accEl = document.getElementById('avgAccuracy');
    const uniqueEl = document.getElementById('uniqueClasses');
    const updateEl = document.getElementById('lastUpdate');

    // Contextos
    const ctxMetrics = document.getElementById('metricsChart').getContext('2d');
    const ctxClasses = document.getElementById('classesChart').getContext('2d');
    const ctxDist = document.getElementById('distributionChart').getContext('2d');
    const ctxRank = document.getElementById('rankingChart').getContext('2d');
    const ctxArea = document.getElementById('stackedAreaChart').getContext('2d');
    const ctxRadar = document.getElementById('radarChart').getContext('2d');
    const ctxScatter = document.getElementById('scatterChart').getContext('2d');
    const ctxHourly = document.getElementById('hourlyChart').getContext('2d');

    let charts = {};

    // ===== MOCK DATA =====
    function generateMock(period) {
        const configs = {
            day:   { labels: ['00h','04h','08h','12h','16h','20h'], n: 6 },
            week:  { labels: ['Seg','Ter','Qua','Qui','Sex','Sáb','Dom'], n: 7 },
            month: { labels: Array.from({length:30}, (_,i)=>`${i+1}`), n: 30 },
            semester: { labels: ['Jan','Fev','Mar','Abr','Mai','Jun'], n: 6 },
            trimestre: { labels: ['Q1','Q2','Q3','Q4'], n: 4 },
            year: { labels: ['Jan','Fev','Mar','Abr','Mai','Jun','Jul','Ago','Set','Out','Nov','Dez'], n: 12 }
        };
        const cfg = configs[period] || configs.week;
        const { labels, n } = cfg;

        // Métricas (predições por período)
        const metricsData = Array.from({ length: n }, () => Math.floor(Math.random() * 80) + 20);

        // Classes (3 classes)
        const classNames = ['Classe A', 'Classe B', 'Classe C'];
        const classData = classNames.map(() =>
            Array.from({ length: n }, () => Math.floor(Math.random() * 30) + 5)
        );

        // Último ponto
        const lastIdx = n - 1;
        const distribution = classData.map(arr => arr[lastIdx]);

        // Ranking (ordenar)
        const ranking = classNames.map((name, i) => ({
            name,
            value: distribution[i]
        })).sort((a,b) => b.value - a.value);

        // Radar: métricas por classe (precisão, recall, f1)
        const radarData = classNames.map(() => ({
            precision: Math.random() * 0.3 + 0.7,
            recall: Math.random() * 0.3 + 0.6,
            f1: Math.random() * 0.3 + 0.65
        }));

        // Scatter: confiança vs latência (100 pontos)
        const scatterPoints = Array.from({ length: 100 }, () => ({
            confidence: Math.random() * 0.5 + 0.5,
            latency: Math.random() * 200 + 50
        }));

        // Hourly (últimas 24h)
        const hourlyLabels = Array.from({ length: 24 }, (_,i) => `${i}h`);
        const hourlyData = Array.from({ length: 24 }, () => Math.floor(Math.random() * 30) + 5);

        // Resumo
        const total = metricsData.reduce((a,b) => a + b, 0);
        const avgAcc = (Math.random() * 0.2 + 0.75).toFixed(2);
        const unique = classNames.length;
        const lastUpdate = new Date().toLocaleString();

        return {
            labels,
            metricsData,
            classData,
            classNames,
            distribution,
            ranking,
            radarData,
            scatterPoints,
            hourlyLabels,
            hourlyData,
            total,
            avgAcc,
            unique,
            lastUpdate
        };
    }

    // ===== DESTROY EXISTENTES =====
    function destroyCharts() {
        Object.values(charts).forEach(chart => {
            if (chart) chart.destroy();
        });
        charts = {};
    }

    // ===== CRIA TODOS OS GRÁFICOS =====
    function renderCharts(data) {
        destroyCharts();

        // 1. Métricas (barras)
        charts.metrics = new Chart(ctxMetrics, {
            type: 'bar',
            data: {
                labels: data.labels,
                datasets: [{ label: 'Predições', data: data.metricsData, backgroundColor: '#f57c00', borderRadius: 4 }]
            },
            options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true } } }
        });

        // 2. Evolução classes (linhas)
        const colors = ['#1e4d2b', '#f57c00', '#e65100'];
        const datasetsLines = data.classData.map((arr, i) => ({
            label: data.classNames[i],
            data: arr,
            borderColor: colors[i % colors.length],
            backgroundColor: 'transparent',
            tension: 0.2,
            pointRadius: 2,
            fill: false
        }));
        charts.classes = new Chart(ctxClasses, {
            type: 'line',
            data: { labels: data.labels, datasets: datasetsLines },
            options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'top' } }, scales: { y: { beginAtZero: true } } }
        });

        // 3. Distribuição (pizza)
        charts.distribution = new Chart(ctxDist, {
            type: 'pie',
            data: {
                labels: data.classNames,
                datasets: [{ data: data.distribution, backgroundColor: ['#1e4d2b','#f57c00','#e65100'], borderColor: '#fff', borderWidth: 2 }]
            },
            options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'bottom' } } }
        });

        // 4. Ranking (barras horizontais)
        const rankLabels = data.ranking.map(item => item.name);
        const rankValues = data.ranking.map(item => item.value);
        charts.ranking = new Chart(ctxRank, {
            type: 'bar',
            data: {
                labels: rankLabels,
                datasets: [{ label: 'Ocorrências', data: rankValues, backgroundColor: ['#1e4d2b','#f57c00','#e65100'], borderRadius: 4 }]
            },
            options: {
                indexAxis: 'y',
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: { x: { beginAtZero: true } }
            }
        });

        // 5. Área empilhada (tendência acumulada)
        const areaDatasets = data.classData.map((arr, i) => ({
            label: data.classNames[i],
            data: arr,
            backgroundColor: colors[i % colors.length] + '66', // transparência
            borderColor: colors[i % colors.length],
            fill: true,
            tension: 0.2,
            pointRadius: 0
        }));
        charts.area = new Chart(ctxArea, {
            type: 'line',
            data: { labels: data.labels, datasets: areaDatasets },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { position: 'top' } },
                scales: { y: { beginAtZero: true, stacked: true } },
                elements: { line: { borderWidth: 2 } }
            }
        });

        // 6. Radar (métricas por classe)
        const radarLabels = ['Precisão', 'Recall', 'F1'];
        const radarColors = ['#1e4d2b', '#f57c00', '#e65100'];
        const radarDatasets = data.classNames.map((name, i) => ({
            label: name,
            data: [ data.radarData[i].precision, data.radarData[i].recall, data.radarData[i].f1 ],
            borderColor: radarColors[i % radarColors.length],
            backgroundColor: radarColors[i % radarColors.length] + '33',
            pointRadius: 4
        }));
        charts.radar = new Chart(ctxRadar, {
            type: 'radar',
            data: { labels: radarLabels, datasets: radarDatasets },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { position: 'bottom' } },
                scales: { r: { min: 0, max: 1, ticks: { stepSize: 0.2 } } }
            }
        });

        // 7. Scatter (confiança vs latência)
        const scatterData = data.scatterPoints.map(p => ({ x: p.confidence, y: p.latency }));
        charts.scatter = new Chart(ctxScatter, {
            type: 'scatter',
            data: {
                datasets: [{
                    label: 'Predições',
                    data: scatterData,
                    backgroundColor: '#f57c00',
                    pointRadius: 4
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                    x: { title: { display: true, text: 'Confiança' }, min: 0.4, max: 1 },
                    y: { title: { display: true, text: 'Latência (ms)' }, beginAtZero: true }
                }
            }
        });

        // 8. Previsões por hora (barras)
        charts.hourly = new Chart(ctxHourly, {
            type: 'bar',
            data: {
                labels: data.hourlyLabels,
                datasets: [{ label: 'Predições', data: data.hourlyData, backgroundColor: '#1e4d2b', borderRadius: 3 }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: { y: { beginAtZero: true } }
            }
        });
    }

    // ===== ATUALIZA DASHBOARD =====
    function updateDashboard(period) {
        const data = generateMock(period);

        // Cards
        totalEl.textContent = data.total;
        accEl.textContent = `${(parseFloat(data.avgAcc) * 100).toFixed(1)}%`;
        uniqueEl.textContent = data.unique;
        updateEl.textContent = data.lastUpdate;

        // Gráficos
        renderCharts(data);
    }

    // ===== EVENTOS =====
    periodSelect.addEventListener('change', () => updateDashboard(periodSelect.value));
    refreshBtn.addEventListener('click', () => updateDashboard(periodSelect.value));

    // ===== INICIALIZA =====
    updateDashboard('week');

})();