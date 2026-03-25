const panel = document.getElementById("attendanceOverviewPanel");
const ctx = document.getElementById("attendanceChart");

function parseCount(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : 0;
}

if (panel && ctx) {
  const presentCount = parseCount(panel.dataset.present);
  const absentCount = parseCount(panel.dataset.absent);
  const totalCount = parseCount(panel.dataset.total) || (presentCount + absentCount);

  const safeTotal = totalCount > 0 ? totalCount : 1;
  const presentPct = ((presentCount / safeTotal) * 100).toFixed(1);
  const absentPct = ((absentCount / safeTotal) * 100).toFixed(1);
  const overallPct = totalCount > 0 ? presentPct : "0.0";

  const presentPercentText = document.getElementById("presentPercentText");
  const absentPercentText = document.getElementById("absentPercentText");
  const attendancePercentValue = document.getElementById("attendancePercentValue");

  if (presentPercentText) presentPercentText.textContent = `${presentPct}%`;
  if (absentPercentText) absentPercentText.textContent = `${absentPct}%`;
  if (attendancePercentValue) attendancePercentValue.textContent = `${overallPct}%`;

  new Chart(ctx, {
    type: "pie",
    data: {
      labels: ["Present", "Absent"],
      datasets: [{
        data: [presentCount, absentCount],
        backgroundColor: ["#16A34A", "#DC2626"],
        borderColor: "#FFFFFF",
        borderWidth: 2
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: true,
      animation: {
        duration: 900,
        easing: "easeOutQuart"
      },
      plugins: {
        legend: {
          display: false
        },
        tooltip: {
          callbacks: {
            label(context) {
              const label = context.label || "";
              const value = Number(context.raw) || 0;
              const pct = totalCount > 0 ? ((value / totalCount) * 100).toFixed(1) : "0.0";
              return `${label}: ${value} (${pct}%)`;
            }
          }
        }
      }
    }
  });
}