import tkinter as tk
from tkinter import ttk, messagebox
import automacao_servopa
import threading
import sys
import os

class TextRedirector:
    def __init__(self, widget):
        self.widget = widget

    def write(self, st):
        self.widget.config(state=tk.NORMAL)
        self.widget.insert(tk.END, st)
        self.widget.see(tk.END)
        self.widget.config(state=tk.DISABLED)

    def flush(self):
        pass

class AutomationApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Automação Servopa - Lances 2")
        self.root.geometry("600x600")
        self.automation_thread = None
        self.stop_automation_flag = threading.Event()
        self.success_count = 0
        self.error_count = 0

        self.consultores_list = self.get_consultores()
        self.create_widgets()
        self.redirect_stdout()

    def get_consultores(self):
        lances_dir = os.path.abspath("Lances")
        if not os.path.exists(lances_dir):
            os.makedirs(lances_dir)
            return []
        try:
            return sorted([d for d in os.listdir(lances_dir) if os.path.isdir(os.path.join(lances_dir, d))])
        except OSError as e:
            messagebox.showerror("Erro de Diretório", f"Não foi possível ler o diretório de Lances: {e}")
            return []

    def create_widgets(self):
        input_frame = tk.Frame(self.root)
        input_frame.pack(pady=10)

        label_consultor = tk.Label(input_frame, text="Nome do Consultor:")
        label_consultor.pack(side=tk.LEFT, padx=5)

        self.entry_consultor = ttk.Combobox(input_frame, width=30, values=self.consultores_list)
        self.entry_consultor.pack(side=tk.LEFT, padx=5)
        self.entry_consultor.focus_set()

        # Título para os resultados
        self.results_title_label = tk.Label(self.root, text="", font=("Helvetica", 10, "bold"))
        self.results_title_label.pack(pady=(10, 0))

        counter_frame = tk.Frame(self.root)
        counter_frame.pack(pady=5)

        self.success_label = tk.Label(counter_frame, text="Lances Registrados: 0", fg="green")
        self.success_label.pack(side=tk.LEFT, padx=10)

        self.error_label = tk.Label(counter_frame, text="Cotas com Erro: 0", fg="red")
        self.error_label.pack(side=tk.LEFT, padx=10)

        # Botões de controle
        self.btn_start = tk.Button(self.root, text="Iniciar Automação", command=self.start_automation_threaded)
        self.btn_start.pack(pady=5)

        self.btn_stop = tk.Button(self.root, text="Finalizar Automação", command=self.stop_automation, state=tk.DISABLED, bg="#FF5733")
        self.btn_stop.pack(pady=5)

        self.log_text = tk.Text(self.root, wrap=tk.WORD, height=20, width=70, state=tk.DISABLED)
        self.log_text.pack(pady=10)

        self.entry_consultor.bind("<Return>", self.start_automation_on_enter)
        self.root.bind("<Return>", self.start_automation_on_enter)

    def redirect_stdout(self):
        sys.stdout = TextRedirector(self.log_text)

    def start_automation_on_enter(self, event=None):
        self.start_automation_threaded()

    def update_counters(self, status):
        if status == "success":
            self.success_count += 1
            self.success_label.config(text=f"Lances Registrados: {self.success_count}")
        else:
            self.error_count += 1
            self.error_label.config(text=f"Cotas com Erro: {self.error_count}")

    def start_automation_threaded(self):
        if self.automation_thread and self.automation_thread.is_alive():
            print("Uma automação já está em andamento.")
            return

        consultor_name = self.entry_consultor.get().strip()
        if not consultor_name:
            messagebox.showwarning("Aviso", "Por favor, insira o nome do consultor.")
            return

        self.stop_automation_flag.clear()
        self.success_count = 0
        self.error_count = 0
        self.results_title_label.config(text=f"Resultados para: {consultor_name}")
        self.success_label.config(text="Lances Registrados: 0")
        self.error_label.config(text="Cotas com Erro: 0")
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete(1.0, tk.END)
        self.log_text.insert(tk.END, f"Iniciando automação para o consultor: {consultor_name}...")
        self.log_text.config(state=tk.DISABLED)

        self.btn_start.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL)
        self.entry_consultor.config(state=tk.DISABLED)
        
        self.automation_thread = threading.Thread(target=automacao_servopa.main, args=(consultor_name, self.update_counters, self.stop_automation_flag))
        self.automation_thread.start()
        
        self.check_automation_thread()

    def stop_automation(self):
        if self.automation_thread and self.automation_thread.is_alive():
            print("\n--- SINAL DE PARADA ENVIADO ---\nA automação será encerrada após a conclusão da cota atual.")
            self.stop_automation_flag.set()
            self.btn_stop.config(state=tk.DISABLED) # Desabilita para evitar cliques múltiplos

    def check_automation_thread(self):
        if self.automation_thread and self.automation_thread.is_alive():
            self.root.after(100, self.check_automation_thread)
        else:
            messagebox.showinfo("Concluído", "Automação finalizada. Verifique a janela para os detalhes.")
            self.btn_start.config(state=tk.NORMAL)
            self.btn_stop.config(state=tk.DISABLED)
            self.entry_consultor.config(state=tk.NORMAL)

if __name__ == "__main__":
    root = tk.Tk()
    app = AutomationApp(root)
    root.mainloop()
