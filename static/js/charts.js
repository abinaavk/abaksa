// charts.js
// Looks for <canvas data-chart="line-or-bar" data-chart-json="element-id">
// on the page and turns each one into a Chart.js chart, reading its data
// out of a <script type="application/json"> tag that Jinja rendered.
// This keeps chart data completely separate from chart drawing code.
//
// Charts also repaint their colors automatically when you flip the
// dark/light theme switch, since Chart.js caches colors at creation time
// otherwise and would look wrong after a toggle.

(function () {
  var activeCharts = [];

  function themeColor(varName) {
    return getComputedStyle(document.documentElement).getPropertyValue(varName).trim();
  }

  function buildChartColors() {
    return {
      text: themeColor("--text-soft"),
      grid: themeColor("--border"),
      primary: themeColor("--primary"),
      primarySoft: themeColor("--primary-soft"),
      success: themeColor("--success"),
      warning: themeColor("--warning"),
      danger: themeColor("--danger"),
    };
  }

  function hexToRgba(hex, alpha) {
    // Chart.js fill colors need rgba, but our CSS vars are hex - this is
    // a tiny converter so we can do translucent fills under line charts
    var clean = hex.replace("#", "");
    if (clean.length === 3) {
      clean = clean.split("").map(function (c) { return c + c; }).join("");
    }
    var bigint = parseInt(clean, 16);
    var r = (bigint >> 16) & 255;
    var g = (bigint >> 8) & 255;
    var b = bigint & 255;
    return "rgba(" + r + "," + g + "," + b + "," + alpha + ")";
  }

  function buildLineChart(canvas, payload, colors) {
    return new Chart(canvas, {
      type: "line",
      data: {
        labels: payload.labels,
        datasets: [{
          label: payload.label || "",
          data: payload.values,
          borderColor: colors.primary,
          backgroundColor: hexToRgba(colors.primary, 0.12),
          fill: true,
          tension: 0.35,
          pointRadius: 3,
          pointBackgroundColor: colors.primary,
        }],
      },
      options: baseOptions(colors, payload),
    });
  }

  function buildBarChart(canvas, payload, colors) {
    var palette = [colors.primary, colors.success, colors.warning, colors.danger];
    return new Chart(canvas, {
      type: "bar",
      data: {
        labels: payload.labels,
        datasets: [{
          label: payload.label || "",
          data: payload.values,
          backgroundColor: payload.labels.map(function (_, i) { return palette[i % palette.length]; }),
          borderRadius: 6,
          maxBarThickness: 46,
        }],
      },
      options: baseOptions(colors, payload),
    });
  }

  function baseOptions(colors, payload) {
    return {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: colors.text === "" ? "#222" : undefined,
        },
      },
      scales: {
        x: {
          ticks: { color: colors.text, font: { size: 11 } },
          grid: { color: "transparent" },
        },
        y: {
          beginAtZero: true,
          ticks: { color: colors.text, font: { size: 11 } },
          grid: { color: colors.grid },
        },
      },
    };
  }

  function initCharts() {
    var colors = buildChartColors();
    var canvases = document.querySelectorAll("canvas[data-chart]");

    canvases.forEach(function (canvas) {
      var jsonId = canvas.getAttribute("data-chart-json");
      var dataEl = document.getElementById(jsonId);
      if (!dataEl) {
        return;
      }
      var payload;
      try {
        payload = JSON.parse(dataEl.textContent);
      } catch (e) {
        return;
      }

      var type = canvas.getAttribute("data-chart");
      var chart;
      if (type === "line") {
        chart = buildLineChart(canvas, payload, colors);
      } else if (type === "bar") {
        chart = buildBarChart(canvas, payload, colors);
      }
      if (chart) {
        activeCharts.push(chart);
      }
    });
  }

  document.addEventListener("DOMContentLoaded", initCharts);

  document.addEventListener("abaksa:themechange", function () {
    var colors = buildChartColors();
    activeCharts.forEach(function (chart) {
      var opts = chart.options;
      opts.scales.x.ticks.color = colors.text;
      opts.scales.y.ticks.color = colors.text;
      opts.scales.y.grid.color = colors.grid;
      if (chart.config.type === "line") {
        chart.data.datasets[0].borderColor = colors.primary;
        chart.data.datasets[0].backgroundColor = hexToRgba(colors.primary, 0.12);
        chart.data.datasets[0].pointBackgroundColor = colors.primary;
      }
      chart.update();
    });
  });
})();
