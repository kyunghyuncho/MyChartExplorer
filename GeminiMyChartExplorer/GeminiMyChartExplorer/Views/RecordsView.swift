import SwiftUI

struct RecordsView: View {
    @EnvironmentObject var appState: AppState
    @StateObject private var viewModel = RecordsViewModel()
    
    // State to track which table is selected in the sidebar
    @State private var selection: String?

    var body: some View {
        // 1. Use NavigationSplitView for a master-detail layout.
        NavigationSplitView {
            // Sidebar (Master View)
            List(viewModel.tableNames, id: \.self, selection: $selection) { tableName in
                Text(tableName).tag(tableName)
            }
            .navigationSplitViewColumnWidth(min: 180, ideal: 200)
            .navigationTitle("Tables")
        } detail: {
            // Main Content (Detail View)
            NavigationStack {
                Group {
                    if !appState.isDatabaseReady {
                        PlaceholderView(
                            imageName: "icloud.slash",
                            title: "Database Not Ready",
                            subtitle: "Please go to the 'Importer' tab to create or open a database file."
                        )
                    } else if viewModel.isLoading {
                        ProgressView("Loading Records...")
                    } else if viewModel.clinicalRecord == nil {
                        PlaceholderView(
                            imageName: "questionmark.folder",
                            title: "No Records Found",
                            subtitle: "The database is open but contains no patient records."
                        )
                    } else {
                        recordList
                    }
                }
                .navigationTitle("Medical Records")
                .onAppear {
                    viewModel.setup(appState: appState)
                    // Set an initial selection for the sidebar
                    if selection == nil {
                        selection = viewModel.tableNames.first
                    }
                }
            }
        }
    }
    
    private var recordList: some View {
        ScrollViewReader { proxy in
            List {
                Section("Patient Information") {
                    if let patient = viewModel.clinicalRecord?.patient {
                        VStack(alignment: .leading, spacing: 4) {
                            Text(patient.fullName).font(.title2.bold())
                            Text("DOB: \(patient.dob ?? "N/A") | MRN: \(patient.mrn ?? "N/A")")
                            Text("Gender: \(patient.gender ?? "N/A") | Race: \(patient.race ?? "N/A")")
                        }
                        .padding(.vertical, 8)
                    }
                }
                
                Group {
                    createSection(title: "Problems",for: viewModel.filteredProblems) { problem in
                        Text(problem.problemName ?? "N/A").bold()
                        Text("Onset: \(problem.onsetDate ?? "N/A") | Status: \(problem.status ?? "N/A")")
                    }
                }
                
                Group {
                    createSection(title: "Medications", for: viewModel.filteredMedications) { med in
                        Text(med.medicationName ?? "N/A").bold()
                        Text(med.instructions ?? "No instructions")
                        Text("Started: \(med.startDate ?? "N/A") | Status: \(med.status ?? "N/A")")
                    }
                }

                Group {
                    createSection(title: "Allergies", for: viewModel.filteredAllergies) { allergy in
                        Text(allergy.substance ?? "N/A").bold()
                        Text("Reaction: \(allergy.reaction ?? "N/A") | Status: \(allergy.status ?? "N/A")")
                    }
                }
                
                Group {
                    createSection(title: "Lab Results", for: viewModel.filteredLabResults) { result in
                        Text(result.testName ?? "N/A").bold()
                        Text("Result: \(result.value ?? "") \(result.unit ?? "") | Range: \(result.referenceRange ?? "N/A")")
                        if let interpretation = result.interpretation { Text("Interpretation: \(interpretation)").italic() }
                    }
                }
                
                Group {
                    createSection(title: "Procedures", for: viewModel.filteredProcedures) { proc in
                        Text(proc.procedureName ?? "N/A").bold()
                        Text("Date: \(proc.date ?? "N/A") | Provider: \(proc.provider ?? "N/A")")
                    }
                }
                
                Group {
                    createSection(title: "Immunizations", for: viewModel.filteredImmunizations) { imm in
                        Text(imm.vaccineName ?? "N/A").bold()
                        Text("Administered: \(imm.dateAdministered ?? "N/A")")
                    }
                }
                
                Group {
                    createSection(title: "Vitals", for: viewModel.filteredVitals) { vital in
                        Text(vital.vitalSign ?? "N/A").bold()
                        Text("\(vital.value ?? "N/A") \(vital.unit ?? "") | Date: \(vital.effectiveDate ?? "N/A")")
                    }
                }
                
                Group {
                    createSection(title: "Notes", for: viewModel.filteredNotes) { note in
                        Text(note.noteTitle ?? "N/A").bold()
                        Text("Type: \(note.noteType ?? "N/A") | Date: \(note.noteDate ?? "N/A")")
                        Text(note.noteContent ?? "No content.").lineLimit(3)
                    }
                }
            }
            .searchable(text: $viewModel.searchText, prompt: "Search All Records")
            .onChange(of: selection) { newSelection in
                print("Selection changed to: \(newSelection ?? "nil")")
                
                guard let newSelection else { return }
                
                print("Attempting to scroll to ID: '\(newSelection)'")
                
                DispatchQueue.main.async {
                    withAnimation {
                        proxy.scrollTo(newSelection, anchor: .top)
                    }
                }
            }
        }
    }
    
    /// A helper function to reduce repetitive code when creating list sections.
    @ViewBuilder
    private func createSection<T: MedicalRecord & Identifiable, Content: View>(
        title: String,
        for data: [T],
        @ViewBuilder rowContent: @escaping (T) -> Content
    ) -> some View {
        // This helper remains unchanged.
        if !data.isEmpty {
            Section(title) {
                ForEach(data) { item in
                    VStack(alignment: .leading, spacing: 2) {
                        rowContent(item)
                    }
                    .padding(.vertical, 4)
                }
            }
            .id(title)
        }
    }
}
