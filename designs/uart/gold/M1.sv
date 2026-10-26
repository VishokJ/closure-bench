// Gold testbench for M1 (R1 + R2 + R3 in one run).
// Proves the three receiver targets are reachable together: an overrun
// (3C left unread, then A5), a false start (17-clock glitch), then a frame
// with a low stop bit. The frame error comes last: after it the line is still
// low, so the receiver may start a spurious frame, which must not disturb the
// other two targets. Self-checking: fails unless each event happens.
`timescale 1ns / 1ps

module tb;

  localparam logic [15:0] PRESCALE = 16'd5;
  localparam int BIT = 5 * 8;

  logic        clk = 1'b0;
  logic        rst = 1'b0;
  logic        rxd = 1'b1;
  logic        m_axis_tready = 1'b0;
  wire  [7:0]  m_axis_tdata;
  wire         m_axis_tvalid, busy, overrun_error, frame_error;

  always #4 clk = ~clk;

  uart_rx dut (
    .clk(clk), .rst(rst),
    .m_axis_tdata(m_axis_tdata), .m_axis_tvalid(m_axis_tvalid), .m_axis_tready(m_axis_tready),
    .rxd(rxd), .busy(busy), .overrun_error(overrun_error), .frame_error(frame_error),
    .prescale(PRESCALE)
  );

  int n_ovr = 0, n_fe = 0;
  logic [7:0] ovr_data;

  always @(negedge clk) begin
    if (overrun_error) begin n_ovr++; ovr_data = m_axis_tdata; end
    if (frame_error) n_fe++;
  end

  // Drive on the falling edge so inputs are stable at every rising edge.
  task automatic wait_clks(input int n);
    repeat (n) @(negedge clk);
  endtask

  task automatic send_frame(input logic [7:0] b, input bit stop);
    rxd = 1'b0; wait_clks(BIT);
    for (int i = 0; i < 8; i++) begin rxd = b[i]; wait_clks(BIT); end
    rxd = stop; wait_clks(BIT);
    rxd = 1'b1;
  endtask

  bit seen_busy;

  initial begin
    @(negedge clk);
    rst = 1'b1; wait_clks(2);
    rst = 1'b0; wait_clks(5);

    // R3: first word left unread, second word overruns it.
    send_frame(8'h3C, 1'b1); wait_clks(4);
    if (!(m_axis_tvalid && m_axis_tdata == 8'h3C)) $fatal(1, "first word not pending");
    send_frame(8'hA5, 1'b1); wait_clks(4);
    if (n_ovr != 1 || ovr_data != 8'hA5) $fatal(1, "no overrun with A5 (n=%0d)", n_ovr);
    m_axis_tready = 1'b1; wait_clks(2);
    if (m_axis_tvalid) $fatal(1, "word not consumed");

    // R2: a low glitch shorter than the mid-start-bit sample point.
    wait_clks(10);
    seen_busy = 0;
    rxd = 1'b0;
    repeat (17) begin @(negedge clk); if (busy) seen_busy = 1; end
    rxd = 1'b1;
    if (!seen_busy) $fatal(1, "receiver never started on the glitch");
    wait_clks(10);
    if (busy) $fatal(1, "receiver still busy after false start");
    if (m_axis_tvalid || n_fe != 0) $fatal(1, "false start produced output");

    // R1: a frame whose stop bit is low.
    wait_clks(100);
    send_frame(8'h55, 1'b0);
    wait_clks(12 * BIT);  // let a spurious frame started by the low stop bit finish
    if (n_fe == 0) $fatal(1, "frame_error never pulsed");

    $display("PASS gold M1");
    $finish;
  end

  initial begin
    #1ms;
    $fatal(1, "timeout");
  end

endmodule
