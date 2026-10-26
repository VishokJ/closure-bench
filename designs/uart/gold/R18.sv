// gold_source: formal
// closure_core.formal.cover_witness: depth 157, input_changes 7, bound 300, witness abf45a488dcb313f
// Formal witness for R18_overrun_then_accept_newest (closure_core/formal.py): the shortest legal input
// trace Yosys/SymbiYosys found (157 cycles), replayed on the uart_rx ports.
// A gold candidate, never shown to an agent; Verilator decides whether it hits.
`timescale 1ns / 1ps

module tb;
  logic clk = 1'b0;
  always #5 clk = ~clk;
  logic rst = 1'd1;
  logic rxd = 1'd0;
  logic m_axis_tready = 1'd0;
  logic [15:0] prescale = 16'd1;
  wire  [7:0] m_axis_tdata;
  wire  m_axis_tvalid;
  wire  busy;
  wire  overrun_error;
  wire  frame_error;

  uart_rx dut (.clk(clk), .rst(rst), .rxd(rxd), .m_axis_tready(m_axis_tready), .prescale(prescale), .m_axis_tdata(m_axis_tdata), .m_axis_tvalid(m_axis_tvalid), .busy(busy), .overrun_error(overrun_error), .frame_error(frame_error));

  initial begin
    @(negedge clk);
    rst = 1'd0;
    repeat (27) @(negedge clk);
    rxd = 1'd1;
    repeat (49) @(negedge clk);
    rxd = 1'd0;
    repeat (8) @(negedge clk);
    rxd = 1'd1;
    repeat (13) @(negedge clk);
    rxd = 1'd0;
    repeat (38) @(negedge clk);
    rxd = 1'd1;
    repeat (19) @(negedge clk);
    m_axis_tready = 1'd1;
    repeat (3) @(negedge clk);
    $finish;
  end
endmodule
