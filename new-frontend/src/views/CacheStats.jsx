import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { getCacheStats, clearCache } from "../api/backend";
import "../print.css";

export default function CacheStats() {
  const navigate = useNavigate();
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [alert, setAlert] = useState({ message: "", type: "" });

  const loadStats = async () => {
    try {
      setLoading(true);
      const data = await getCacheStats();
      setStats(data);
      setError(null);
    } catch (err) {
      setError("Error loading cache stats: " + err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadStats();
    // Auto-refresh cada 10 segundos
    const interval = setInterval(loadStats, 10000);
    return () => clearInterval(interval);
  }, []);

  const handleClearCache = async (type) => {
    const confirmMessages = {
      all: "This will clear ALL caches (RAM + Disk). Are you sure?",
      grid2d: "Clear Grid2D cache (RAM)?",
      w_operator_ram: "Clear W Operator RAM cache?",
      w_operator_disk: "Clear W Operator Disk cache (.npz files)?",
    };
    const confirmMsg = confirmMessages[type] || `Clear ${type} cache?`;

    if (!window.confirm(confirmMsg)) return;

    try {
      const result = await clearCache(type);
      setAlert({
        message: `Successfully cleared ${result.cleared} entries from ${type} cache`,
        type: "success",
      });
      setTimeout(() => setAlert({ message: "", type: "" }), 5000);
      loadStats();
    } catch (err) {
      setAlert({
        message: "Error clearing cache: " + err.message,
        type: "error",
      });
      setTimeout(() => setAlert({ message: "", type: "" }), 5000);
    }
  };

  if (loading && !stats) {
    return (
      <div style={styles.container}>
        <div style={styles.loading}>Loading cache stats...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div style={styles.container}>
        <div style={styles.error}>{error}</div>
        <button onClick={loadStats} style={styles.btnPrimary}>
          Retry
        </button>
      </div>
    );
  }

  const grid2d = stats?.grid2d_cache || {
    entries: 0,
    size_mb: 0,
    max_size_mb: 100,
  };
  const wRam = stats?.w_operator_cache_ram || {
    entries: 0,
    size_mb: 0,
    max_size_mb: 300,
  };
  const wDisk = stats?.w_operator_cache_disk || { files: 0, size_mb: 0 };

  return (
    <div style={styles.container}>
      <div style={styles.header}>
        <h1 style={styles.title}>📊 Cache Statistics</h1>
        <button
          onClick={() => navigate("/")}
          style={styles.closeBtn}
          onMouseOver={(e) => {
            e.currentTarget.style.background = "#d1d5db";
            e.currentTarget.style.transform = "scale(1.05)";
          }}
          onMouseOut={(e) => {
            e.currentTarget.style.background = "#e5e7eb";
            e.currentTarget.style.transform = "scale(1)";
          }}
          title="Volver a página principal"
        >
          ✕
        </button>
      </div>

      {alert.message && (
        <div
          style={{
            ...styles.alert,
            ...(alert.type === "success"
              ? styles.alertSuccess
              : styles.alertError),
          }}
        >
          {alert.message}
        </div>
      )}

      <div style={styles.statsContainer}>
        {/* GRID2D Cache */}
        <div style={styles.card}>
          <h2 style={styles.cardTitle}>🗺️ Grid 2D Cache (RAM)</h2>
          <div style={styles.statRow}>
            <span style={styles.statLabel}>Entries:</span>
            <span style={styles.statValue}>{grid2d.entries}</span>
          </div>
          <div style={styles.statRow}>
            <span style={styles.statLabel}>Size:</span>
            <span style={styles.statValue}>{grid2d.size_mb.toFixed(2)} MB</span>
          </div>
          <div style={styles.statRow}>
            <span style={styles.statLabel}>Max:</span>
            <span style={styles.statValue}>{grid2d.max_size_mb} MB</span>
          </div>
          <div style={styles.progressBar}>
            <div
              style={{
                ...styles.progressFill,
                width: `${((grid2d.size_mb / grid2d.max_size_mb) * 100).toFixed(1)}%`,
              }}
            />
          </div>
        </div>

        {/* W Operator RAM */}
        <div style={styles.card}>
          <h2 style={styles.cardTitle}>⚡ W Operator Cache (RAM)</h2>
          <div style={styles.statRow}>
            <span style={styles.statLabel}>Entries:</span>
            <span style={styles.statValue}>{wRam.entries}</span>
          </div>
          <div style={styles.statRow}>
            <span style={styles.statLabel}>Size:</span>
            <span style={styles.statValue}>{wRam.size_mb.toFixed(2)} MB</span>
          </div>
          <div style={styles.statRow}>
            <span style={styles.statLabel}>Max:</span>
            <span style={styles.statValue}>{wRam.max_size_mb} MB</span>
          </div>
          <div style={styles.progressBar}>
            <div
              style={{
                ...styles.progressFill,
                width: `${((wRam.size_mb / wRam.max_size_mb) * 100).toFixed(1)}%`,
              }}
            />
          </div>
        </div>

        {/* W Operator Disk */}
        <div style={styles.card}>
          <h2 style={styles.cardTitle}>💾 W Operator Cache (Disk)</h2>
          <div style={styles.statRow}>
            <span style={styles.statLabel}>Files:</span>
            <span style={styles.statValue}>{wDisk.files}</span>
          </div>
          <div style={styles.statRow}>
            <span style={styles.statLabel}>Size:</span>
            <span style={styles.statValue}>{wDisk.size_mb.toFixed(2)} MB</span>
          </div>
          <div style={styles.statRow}>
            <span style={styles.statLabel}>Location:</span>
            <span style={{ ...styles.statValue, fontSize: "11px" }}>
              app/storage/cache/
            </span>
          </div>
        </div>
      </div>

      <div style={styles.buttons}>
        <button
          style={styles.btnPrimary}
          onClick={loadStats}
          onMouseOver={(e) => (e.currentTarget.style.opacity = "0.8")}
          onMouseOut={(e) => (e.currentTarget.style.opacity = "1")}
        >
          🔄 Refresh
        </button>
        <button
          style={styles.btnDanger}
          onClick={() => handleClearCache("grid2d")}
          onMouseOver={(e) => (e.currentTarget.style.opacity = "0.8")}
          onMouseOut={(e) => (e.currentTarget.style.opacity = "1")}
        >
          Clear Grid2D
        </button>
        <button
          style={styles.btnDanger}
          onClick={() => handleClearCache("w_operator_ram")}
          onMouseOver={(e) => (e.currentTarget.style.opacity = "0.8")}
          onMouseOut={(e) => (e.currentTarget.style.opacity = "1")}
        >
          Clear W Operator RAM
        </button>
        <button
          style={styles.btnDanger}
          onClick={() => handleClearCache("w_operator_disk")}
          onMouseOver={(e) => (e.currentTarget.style.opacity = "0.8")}
          onMouseOut={(e) => (e.currentTarget.style.opacity = "1")}
        >
          Clear W Operator Disk
        </button>
        <button
          style={styles.btnDanger}
          onClick={() => handleClearCache("all")}
          onMouseOver={(e) => (e.currentTarget.style.opacity = "0.8")}
          onMouseOut={(e) => (e.currentTarget.style.opacity = "1")}
        >
          ⚠️ Clear All
        </button>
      </div>

      {/* Lista de archivos en cache */}
      <div style={styles.filesSection}>
        <h2 style={styles.filesSectionTitle}>
          📁 Cache Files ({stats?.cache_files?.length || 0})
        </h2>
        {stats?.cache_files && stats.cache_files.length > 0 ? (
          <div style={styles.filesTable}>
            <div style={styles.tableHeader}>
              <div style={styles.tableHeaderCell}>Filename</div>
              <div style={{ ...styles.tableHeaderCell, textAlign: "right" }}>
                Size
              </div>
              <div style={{ ...styles.tableHeaderCell, textAlign: "right" }}>
                Modified
              </div>
            </div>
            <div style={styles.tableBody}>
              {stats.cache_files.map((file, index) => (
                <div
                  key={index}
                  style={styles.tableRow}
                  onMouseOver={(e) => {
                    e.currentTarget.style.backgroundColor = "#f9fafb";
                  }}
                  onMouseOut={(e) => {
                    e.currentTarget.style.backgroundColor = "transparent";
                  }}
                >
                  <div style={styles.tableCell} title={file.name}>
                    {file.name}
                  </div>
                  <div style={{ ...styles.tableCell, textAlign: "right" }}>
                    {file.size_mb >= 0.01
                      ? `${file.size_mb.toFixed(2)} MB`
                      : `${(file.size_bytes / 1024).toFixed(2)} KB`}
                  </div>
                  <div
                    style={{
                      ...styles.tableCell,
                      textAlign: "right",
                      fontSize: "12px",
                    }}
                  >
                    {new Date(file.modified_at * 1000).toLocaleString()}
                  </div>
                </div>
              ))}
            </div>
          </div>
        ) : (
          <div style={styles.emptyState}>
            <p>No cache files found</p>
          </div>
        )}
      </div>

      <div style={styles.timestamp}>
        Last updated: {new Date().toLocaleString()}
      </div>
    </div>
  );
}

const styles = {
  container: {
    fontFamily:
      "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
    maxWidth: "1200px",
    margin: "40px auto",
    padding: "20px",
    background: "#f5f5f5",
    minHeight: "calc(100vh - 80px)",
  },
  header: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: "30px",
  },
  title: {
    color: "#333",
    margin: 0,
  },
  closeBtn: {
    background: "#e5e7eb",
    border: "none",
    borderRadius: "6px",
    padding: "8px 16px",
    fontSize: "20px",
    cursor: "pointer",
    fontWeight: "bold",
    color: "#333",
    transition: "all 0.2s ease",
  },
  statsContainer: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))",
    gap: "20px",
    margin: "30px 0",
  },
  card: {
    background: "white",
    borderRadius: "8px",
    padding: "20px",
    boxShadow: "0 2px 8px rgba(0,0,0,0.1)",
  },
  cardTitle: {
    marginTop: 0,
    color: "#2563eb",
    fontSize: "18px",
  },
  statRow: {
    display: "flex",
    justifyContent: "space-between",
    padding: "8px 0",
    borderBottom: "1px solid #eee",
  },
  statLabel: {
    color: "#666",
  },
  statValue: {
    fontWeight: 600,
    color: "#333",
  },
  progressBar: {
    width: "100%",
    height: "20px",
    background: "#e5e7eb",
    borderRadius: "10px",
    overflow: "hidden",
    marginTop: "10px",
  },
  progressFill: {
    height: "100%",
    background: "linear-gradient(90deg, #3b82f6, #2563eb)",
    transition: "width 0.3s ease",
  },
  buttons: {
    display: "flex",
    gap: "10px",
    marginTop: "20px",
    flexWrap: "wrap",
  },
  btnPrimary: {
    padding: "10px 20px",
    border: "none",
    borderRadius: "6px",
    cursor: "pointer",
    fontSize: "14px",
    fontWeight: 500,
    background: "#2563eb",
    color: "white",
  },
  btnDanger: {
    padding: "10px 20px",
    border: "none",
    borderRadius: "6px",
    cursor: "pointer",
    fontSize: "14px",
    fontWeight: 500,
    background: "#dc2626",
    color: "white",
  },
  timestamp: {
    fontSize: "12px",
    color: "#999",
    marginTop: "20px",
  },
  alert: {
    padding: "15px",
    borderRadius: "6px",
    marginBottom: "20px",
  },
  alertSuccess: {
    background: "#d1fae5",
    color: "#065f46",
    border: "1px solid #6ee7b7",
  },
  alertError: {
    background: "#fee2e2",
    color: "#991b1b",
    border: "1px solid #fca5a5",
  },
  loading: {
    textAlign: "center",
    padding: "40px",
    fontSize: "18px",
    color: "#666",
  },
  error: {
    color: "#991b1b",
    background: "#fee2e2",
    padding: "15px",
    borderRadius: "6px",
    marginBottom: "20px",
  },
  filesSection: {
    marginTop: "30px",
    background: "white",
    borderRadius: "8px",
    padding: "20px",
    boxShadow: "0 2px 8px rgba(0,0,0,0.1)",
  },
  filesSectionTitle: {
    margin: "0 0 15px 0",
    color: "#2563eb",
    fontSize: "18px",
  },
  filesTable: {
    width: "100%",
    overflowX: "auto",
  },
  tableHeader: {
    display: "grid",
    gridTemplateColumns: "1fr 120px 180px",
    gap: "10px",
    padding: "10px",
    background: "#f3f4f6",
    borderRadius: "6px 6px 0 0",
    borderBottom: "2px solid #e5e7eb",
    fontWeight: 600,
    fontSize: "13px",
    color: "#374151",
  },
  tableHeaderCell: {
    padding: "0 5px",
  },
  tableBody: {
    maxHeight: "400px",
    overflowY: "auto",
    background: "white",
  },
  tableRow: {
    display: "grid",
    gridTemplateColumns: "1fr 120px 180px",
    gap: "10px",
    padding: "12px 10px",
    borderBottom: "1px solid #e5e7eb",
    transition: "background-color 0.2s ease",
  },
  tableCell: {
    padding: "0 5px",
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
    fontSize: "13px",
    color: "#4b5563",
  },
  emptyState: {
    textAlign: "center",
    padding: "40px 20px",
    color: "#9ca3af",
    fontSize: "14px",
  },
};
