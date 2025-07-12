// CDAXMLParser.swift

import Foundation

/// An error that can occur during XML parsing.
enum ParserError: Error {
    case invalidURL
    case dataLoadingFailed(Error)
    case parsingFailed(Error)
    case patientDataMissing
}

/// A class responsible for parsing Clinical Document Architecture (CDA) XML files.
class XMLFileParser: NSObject, XMLParserDelegate {

    // MARK: - Properties

    private var parsedRecords: ParsedRecords?
    private var root: XMLElement?
    private var currentElement: XMLElement?
    
    /// This dictionary will store the mapping from a namespace URI to its prefix (e.g., "urn:hl7-org:v3" -> "cda").
    private var namespaceMapping: [String: String] = [:]

    private let ns = [
        "cda": "urn:hl7-org:v3",
        "sdtc": "urn:hl7-org:sdtc"
    ]

    // MARK: - Public API

    public func parse(from url: URL, completion: @escaping (Result<ParsedRecords, ParserError>) -> Void) {
        let task = URLSession.shared.dataTask(with: url) { data, _, error in
            if let error = error {
                completion(.failure(ParserError.dataLoadingFailed(error)))
                return
            }
            
            guard let data = data else {
                completion(.failure(ParserError.dataLoadingFailed(URLError(.cannotDecodeContentData))))
                return
            }
            
            do {
                let records = try self.parse(data: data)
                completion(.success(records))
            } catch let parserError as ParserError {
                completion(.failure(parserError))
            } catch {
                completion(.failure(.parsingFailed(error)))
            }
        }
        task.resume()
    }

    // MARK: - Parsing Logic

    private func parse(data: Data) throws -> ParsedRecords {
        let parser = XMLParser(data: data)
        parser.delegate = self
        
        // Note: We no longer need shouldReportNamespacePrefixes, as we build the names manually.
        
        guard parser.parse(), let root = self.root else {
            throw ParserError.parsingFailed(parser.parserError ?? URLError(.cannotParseResponse))
        }

        guard let patient = ingestPatient(from: root) else {
            throw ParserError.patientDataMissing
        }
        self.parsedRecords = ParsedRecords(patient: patient)
        
        let sectionIngestors: [String: (XMLElement) -> Void] = [
            "2.16.840.1.113883.10.20.22.2.6.1": ingestAllergies,
            "2.16.840.1.113883.10.20.22.2.5.1": ingestProblems,
            "2.16.840.1.113883.10.20.22.2.1.1": ingestMedications,
            "2.16.840.1.113883.10.20.22.2.2.1": ingestImmunizations,
            "2.16.840.1.113883.10.20.22.2.4.1": ingestVitals,
            "2.16.840.1.113883.10.20.22.2.3.1": ingestResults,
            "2.16.840.1.113883.10.20.22.2.7.1": ingestProcedures,
            "1.3.6.1.4.1.19376.1.5.3.1.3.4": ingestNotes
        ]

        let allSections = root.findElements(path: ".//cda:section", namespaces: ns)
        
        for section in allSections {
            // find all templateId elements in the section.
            for templateIdElement in section.findElements(path: ".//cda:templateId", namespaces: ns) {
                if let templateId = templateIdElement.attributes["root"] {
                    // Check if we have an ingestor for this template ID.
                    if let ingestor = sectionIngestors[templateId] {
                        print("Ingesting section with template ID: \(templateId)")
                        ingestor(section)
                    }
                }
            }
        }
        
        return self.parsedRecords!
    }
    
    // MARK: - Ingestion Methods (No changes needed here)
    // ... all your ingestPatient, ingestAllergies, etc. methods remain the same ...
    private func ingestPatient(from root: XMLElement) -> Patient? {
        guard let patientRole = root.findElement(path: ".//cda:recordTarget/cda:patientRole", namespaces: ns) else { return nil }
        guard let patientEl = patientRole.findElement(path: "cda:patient", namespaces: ns) else { return nil }

        let givenName = findText(in: patientEl, path: "cda:name/cda:given")
        let familyName = findText(in: patientEl, path: "cda:name/cda:family")
        let dob = findAttrib(in: patientEl, path: "cda:birthTime", attribute: "value")
        let mrn = findAttrib(in: patientRole, path: "cda:id", attribute: "extension")
        
        return Patient(
            mrn: mrn,
            givenName: givenName,
            familyName: familyName,
            dob: dob,
            gender: findAttrib(in: patientEl, path: "cda:administrativeGenderCode", attribute: "displayName"),
            maritalStatus: findAttrib(in: patientEl, path: "cda:maritalStatusCode", attribute: "displayName"),
            race: findAttrib(in: patientEl, path: "cda:raceCode", attribute: "displayName"),
            ethnicity: findAttrib(in: patientEl, path: "cda:ethnicGroupCode", attribute: "displayName"),
            deceased: findAttrib(in: patientEl, path: "sdtc:deceasedInd", attribute: "value") == "true",
            deceasedDate: findAttrib(in: patientEl, path: "sdtc:deceasedTime", attribute: "value")
        )
    }

    private func ingestAllergies(in section: XMLElement) {
        for entry in section.findElements(path: ".//cda:entry", namespaces: ns) {
            if let observation = entry.findElement(path: ".//cda:observation", namespaces: ns),
               observation.attributes["negationInd"] == "true" {
                continue // Skip negated entries
            }

            let allergy = Allergy(
                substance: findNameWithFallback(in: entry, path: ".//cda:participant/cda:participantRole/cda:playingEntity/cda:code"),
                reaction: findAttrib(in: entry, path: ".//cda:entryRelationship/cda:observation/cda:value", attribute: "displayName"),
                status: findAttrib(in: entry, path: ".//cda:act/cda:statusCode", attribute: "code"),
                effectiveDate: findAttrib(in: entry, path: ".//cda:effectiveTime/cda:low", attribute: "value")
            )
            parsedRecords?.allergies.append(allergy)
        }
    }

    private func ingestProblems(in section: XMLElement) {
        for entry in section.findElements(path: ".//cda:entry", namespaces: ns) {
            guard let obs = entry.findElement(path: ".//cda:observation", namespaces: ns) else { continue }
            
            let problem = Problem(
                problemName: findNameWithFallback(in: obs, path: "cda:value"),
                status: findAttrib(in: obs, path: ".//cda:entryRelationship/cda:observation/cda:value", attribute: "displayName"),
                onsetDate: findAttrib(in: obs, path: "cda:effectiveTime/cda:low", attribute: "value"),
                resolvedDate: findAttrib(in: obs, path: "cda:effectiveTime/cda:high", attribute: "value")
            )
            parsedRecords?.problems.append(problem)
        }
    }

    private func ingestMedications(in section: XMLElement) {
        for entry in section.findElements(path: ".//cda:entry/cda:substanceAdministration", namespaces: ns) {
            let medication = Medication(
                medicationName: findNameWithFallback(in: entry, path: ".//cda:consumable/cda:manufacturedProduct/cda:manufacturedMaterial/cda:code"),
                instructions: findNameWithFallback(in: entry, path: "cda:text"),
                status: findAttrib(in: entry, path: "cda:statusCode", attribute: "code"),
                startDate: findAttrib(in: entry, path: "cda:effectiveTime/cda:low", attribute: "value"),
                endDate: findAttrib(in: entry, path: "cda:effectiveTime/cda:high", attribute: "value")
            )
            parsedRecords?.medications.append(medication)
        }
    }
    
    private func ingestImmunizations(in section: XMLElement) {
        for entry in section.findElements(path: ".//cda:entry/cda:substanceAdministration", namespaces: ns) {
            let immunization = Immunization(
                vaccineName: findNameWithFallback(in: entry, path: "cda:consumable/cda:manufacturedProduct/cda:manufacturedMaterial/cda:code"),
                dateAdministered: findAttrib(in: entry, path: "cda:effectiveTime", attribute: "value")
            )
            parsedRecords?.immunizations.append(immunization)
        }
    }
    
    private func ingestVitals(in section: XMLElement) {
        for comp in section.findElements(path: ".//cda:component/cda:observation", namespaces: ns) {
            guard let vitalSign = findNameWithFallback(in: comp, path: "cda:code") else { continue }
            
            let vital = Vital(
                vitalSign: vitalSign,
                value: findAttrib(in: comp, path: "cda:value", attribute: "value"),
                unit: findAttrib(in: comp, path: "cda:value", attribute: "unit"),
                effectiveDate: findAttrib(in: comp, path: "cda:effectiveTime", attribute: "value")
            )
            parsedRecords?.vitals.append(vital)
        }
    }
    
    private func ingestResults(in section: XMLElement) {
        for comp in section.findElements(path: ".//cda:component/cda:observation", namespaces: ns) {
            guard let testName = findNameWithFallback(in: comp, path: "cda:code") else { continue }

            var value: String?
            var unit: String?
            if let valueEl = comp.findElement(path: "cda:value", namespaces: ns) {
                value = valueEl.attributes["value"] ?? valueEl.attributes["displayName"] ?? valueEl.text
                unit = valueEl.attributes["unit"]
            }

            let result = LabResult(
                testName: testName,
                value: value,
                unit: unit,
                referenceRange: findText(in: comp, path: ".//cda:referenceRange/cda:observationRange/cda:text"),
                interpretation: findAttrib(in: comp, path: "cda:interpretationCode", attribute: "displayName"),
                effectiveDate: findAttrib(in: comp, path: "cda:effectiveTime", attribute: "value")
            )
            parsedRecords?.results.append(result)
        }
    }
    
    private func ingestProcedures(in section: XMLElement) {
        for proc in section.findElements(path: ".//cda:entry/cda:procedure", namespaces: ns) {
            let procName = findNameWithFallback(in: proc, path: "cda:code") ?? findNameWithFallback(in: proc, path: ".//cda:participant/cda:participantRole/cda:playingDevice/cda:code")

            let procedure = Procedure(
                procedureName: procName,
                date: findAttrib(in: proc, path: "cda:effectiveTime/cda:low", attribute: "value") ?? findAttrib(in: proc, path: "cda:effectiveTime", attribute: "value"),
                provider: findText(in: proc, path: ".//cda:performer/cda:assignedEntity/cda:assignedPerson/cda:name")
            )
            parsedRecords?.procedures.append(procedure)
        }
    }
    
    private func ingestNotes(in section: XMLElement) {
        guard let textEl = section.findElement(path: "cda:text", namespaces: ns) else { return }
        let noteContent = textEl.recursiveText().trimmingCharacters(in: .whitespacesAndNewlines)
        if noteContent.isEmpty { return }

        let noteTitle = section.findElement(path: "cda:title", namespaces: ns)?.text?.trimmingCharacters(in: .whitespacesAndNewlines) ?? "Clinical Note"
        let noteType = findAttrib(in: section, path: "cda:code", attribute: "displayName") ?? "Note"
        
        let noteDate = root?.findElement(path: ".//cda:encompassingEncounter/cda:effectiveTime/cda:low", namespaces: ns)?.attributes["value"]
                     ?? root?.findElement(path: "cda:effectiveTime", namespaces: ns)?.attributes["value"]
        
        let provider = root?.findElement(path: ".//cda:encompassingEncounter//cda:assignedPerson/cda:name", namespaces: ns)?.recursiveText().trimmingCharacters(in: .whitespacesAndNewlines)

        let note = Note(
            noteType: noteType,
            noteDate: noteDate,
            noteTitle: noteTitle,
            noteContent: noteContent,
            provider: provider
        )
        parsedRecords?.notes.append(note)
    }

    // MARK: - Helper Methods (No changes needed here)
    // ... all your findText, findAttrib, etc. methods remain the same ...
    private func findText(in element: XMLElement?, path: String) -> String? {
        return element?.findElement(path: path, namespaces: ns)?.text?.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private func findAttrib(in element: XMLElement?, path: String, attribute: String) -> String? {
        return element?.findElement(path: path, namespaces: ns)?.attributes[attribute]
    }
    
    private func findNameWithFallback(in element: XMLElement?, path: String) -> String? {
        guard let codeEl = element?.findElement(path: path, namespaces: ns) else { return nil }
        
        // 1. Try 'displayName' attribute first.
        if let displayName = codeEl.attributes["displayName"], !displayName.isEmpty {
            return displayName
        }
        
        // 2. Fallback to 'originalText'.
        if let originalTextEl = codeEl.findElement(path: "originalText", namespaces: ns) {
            // Look for simple text inside <originalText>
            if let text = originalTextEl.text, !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                return text.trimmingCharacters(in: .whitespacesAndNewlines)
            }
            
            // 3. CORRECTED: Fallback to resolving a reference within <originalText>.
            // This now correctly uses the parser's top-level `self.root` to search the whole document.
            if let referenceEl = originalTextEl.findElement(path: "reference", namespaces: ns),
               let refId = referenceEl.attributes["value"], refId.starts(with: "#") {
                
                let idToFind = String(refId.dropFirst())
                if let referencedEl = self.root?.findElement(byID: idToFind) {
                    return referencedEl.recursiveText().trimmingCharacters(in: .whitespacesAndNewlines)
                }
            }
        }
        
        // 4. As a final fallback, use the text of the code element itself if available.
        if let text = codeEl.text, !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            return text.trimmingCharacters(in: .whitespacesAndNewlines)
        }
        
        return nil
    }


    // MARK: - XMLParserDelegate Methods

    func parserDidStartDocument(_ parser: XMLParser) {
        // Reset all state for the new document
        root = nil
        currentElement = nil
        namespaceMapping = [:]
    }

    func parser(_ parser: XMLParser, didStartElement elementName: String, namespaceURI: String?, qualifiedName qName: String?, attributes attributeDict: [String : String] = [:]) {
        // 1. Learn namespace prefixes from attributes as we encounter them (e.g., "xmlns:cda")
        for (key, value) in attributeDict where key.starts(with: "xmlns:") {
            let prefix = String(key.dropFirst(6)) // "cda"
            namespaceMapping[value] = prefix // Map the URI to the prefix
        }
        
        // 2. Manually construct the element name with its prefix
        var finalElementName = elementName
        if let uri = namespaceURI, let prefix = namespaceMapping[uri] {
            finalElementName = "\(prefix):\(elementName)"
        }
        
        // 3. Create the element and add it to the tree
        let newElement = XMLElement(name: finalElementName, attributes: attributeDict)
        newElement.parent = currentElement
        currentElement?.children.append(newElement)
        
        if root == nil {
            root = newElement
        }
        currentElement = newElement
    }

    func parser(_ parser: XMLParser, foundCharacters string: String) {
        currentElement?.text = (currentElement?.text ?? "") + string
    }

    func parser(_ parser: XMLParser, didEndElement elementName: String, namespaceURI: String?, qualifiedName qName: String?) {
        currentElement = currentElement?.parent
    }

    func parser(_ parser: XMLParser, parseErrorOccurred parseError: Error) {
        // Errors are handled by the throwing parse() function
    }
}

/// A helper class to represent an XML element as a navigable tree structure.
class XMLElement {
    let name: String
    let attributes: [String: String]
    var children: [XMLElement] = []
    var text: String?
    weak var parent: XMLElement?

    init(name: String, attributes: [String: String]) {
        self.name = name
        self.attributes = attributes
    }
    
    func recursiveText() -> String {
        return (text ?? "").trimmingCharacters(in: .whitespacesAndNewlines) + children.map { $0.recursiveText() }.joined(separator: " ")
    }

    func findElement(byID id: String) -> XMLElement? {
        if self.attributes["ID"] == id {
            return self
        }
        for child in children {
            if let found = child.findElement(byID: id) {
                return found
            }
        }
        return nil
    }
    
    func findElement(path: String, namespaces: [String: String]) -> XMLElement? {
        return findElements(path: path, namespaces: namespaces).first
    }
    
    func findElements(path: String, namespaces: [String: String]) -> [XMLElement] {
        // --- ADDED LOGIC ---
        // Start with the original path.
        var sanitizedPath = path
        
        // Programmatically remove any prefixes found in the 'ns' dictionary.
        for prefix in namespaces.keys {
            sanitizedPath = sanitizedPath.replacingOccurrences(of: "\(prefix):", with: "")
        }
        // --- END ADDED LOGIC ---

        let isRecursive = sanitizedPath.starts(with: ".//")
        let finalPath = isRecursive ? String(sanitizedPath.dropFirst(3)) : sanitizedPath
        let components = finalPath.split(separator: "/").map(String.init)
        
        guard let firstComponent = components.first else { return [] }
        
        var currentElements: [XMLElement]
        
        if isRecursive {
            currentElements = self.findDescendants(named: firstComponent)
        } else {
            currentElements = self.children.filter { $0.name == firstComponent }
        }
        
        let remainingComponents = components.dropFirst()
        for component in remainingComponents {
            var nextElements: [XMLElement] = []
            for element in currentElements {
                nextElements.append(contentsOf: element.children.filter { $0.name == component })
            }
            currentElements = nextElements
        }
        
        return currentElements
    }
    
    private func findDescendants(named name: String) -> [XMLElement] {
        var found: [XMLElement] = []
        for child in self.children {
            if child.name == name {
                found.append(child)
            }
            found.append(contentsOf: child.findDescendants(named: name))
        }
        return found
    }
}
